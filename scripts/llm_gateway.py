#!/usr/bin/env python3
"""LLM gateway to call multiple backend providers with retry/fallback and basic logging.

This is a small abstraction that reads a backends YAML, selects a model for the
given task (analysis/embeddings), posts the prepared prompt, supports simple
OpenAI-compatible and generic HTTP providers, retries, and falls back to a
secondary backend if configured.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import yaml


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--normalized", required=True)
    p.add_argument("--rag", required=False)
    p.add_argument("--backends", required=True)
    p.add_argument("--output-raw", required=True)
    p.add_argument("--output-parsed", required=True)
    p.add_argument("--task", required=False, default="analysis")
    return p.parse_args()


def load_yaml(p: Path) -> Dict[str, Any]:
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def call_backend(backend: Dict[str, Any], prompt: str, model: str, timeout: int) -> requests.Response:
    provider = backend.get("provider")
    url = backend.get("base_url")
    headers = {}
    auth_env = backend.get("auth_env")
    token = os.environ.get(auth_env or "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers["Content-Type"] = "application/json"

    if provider == "openai":
        body = {"model": model, "messages": [{"role": "system", "content": "You are a senior Kubernetes platform operations analyst."}, {"role": "user", "content": prompt}], "temperature": 0}
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        return resp

    # generic HTTP provider expects {model, input}
    body = {"model": model, "input": prompt}
    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    return resp


def main() -> int:
    args = parse_args()
    # Short-circuit to mock mode when environment requests it (dry-run)
    if os.environ.get("MOCK_LLM"):
        raw_out = Path(args.output_raw)
        parsed_out = Path(args.output_parsed)
        raw_out.parent.mkdir(parents=True, exist_ok=True)
        parsed_out.parent.mkdir(parents=True, exist_ok=True)
        # write a fake successful envelope and a simple parsed JSON
        raw = {"status_code": 200, "body": '{"general_health": "Mock OK", "critical_findings": [], "risk_level": "low", "recommended_actions": [], "missing_data": [], "related_runbooks": []}', "meta": {"provider": "mock", "model": "mock-model", "attempts": 1, "latency": 0.0, "fallback_used": False}}
        raw_out.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        parsed = {"general_health": "Mock OK", "critical_findings": [], "risk_level": "low", "recommended_actions": [], "missing_data": [], "related_runbooks": []}
        parsed_out.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        return 0
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    backends_cfg = load_yaml(Path(args.backends))
    mode = backends_cfg.get("llm_mode", "single")
    backends = backends_cfg.get("llm_backends", {})

    primary = backends.get("primary")
    if not primary:
        print("No primary backend configured")
        return 2

    chosen = primary
    attempts = 0
    fallback_used = False
    last_exception = None
    raw_out = Path(args.output_raw)
    parsed_out = Path(args.output_parsed)

    backoff = 1.0
    while True:
        model = chosen.get("models", {}).get(args.task)
        timeout = chosen.get("timeout", 60)
        retries = chosen.get("retries", 0)
        try:
            attempts += 1
            start = time.time()
            resp = call_backend(chosen, prompt, model, timeout)
            latency = time.time() - start
            meta = {"provider": chosen.get("provider"), "model": model, "attempts": attempts, "latency": latency, "fallback_used": fallback_used}
            # write raw
            raw_out.parent.mkdir(parents=True, exist_ok=True)
            content = resp.text if resp is not None else ""
            out_obj = {"status_code": resp.status_code if resp is not None else None, "body": content, "meta": meta}
            raw_out.write_text(json.dumps(out_obj, indent=2, ensure_ascii=False), encoding="utf-8")

            if resp is not None and resp.status_code == 200:
                # parse via parse_llm_response helper for schema normalization
                subprocess.run(["python3", Path(__file__).parent.joinpath("parse_llm_response.py"), "--input", str(raw_out), "--output", str(parsed_out)], check=False)
                # write metadata
                meta_path = parsed_out.with_suffix(parsed_out.suffix + ".meta.json")
                meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                return 0
            else:
                last_exception = Exception(f"Bad status: {resp.status_code if resp is not None else 'n/a'}")
                if retries > 0:
                    retries -= 1
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                # try fallback if configured
                fb = chosen.get("fallback")
                if fb and fb in backends:
                    chosen = backends.get(fb)
                    fallback_used = True
                    attempts = 0
                    continue
                break
        except Exception as e:
            last_exception = e
            if chosen.get("retries", 0) > 0:
                chosen["retries"] -= 1
                time.sleep(backoff)
                backoff *= 2
                continue
            fb = chosen.get("fallback")
            if fb and fb in backends:
                chosen = backends.get(fb)
                fallback_used = True
                attempts = 0
                continue
            break

    # final failure: write raw failure info
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    raw_out.write_text(json.dumps({"error": str(last_exception)}, indent=2), encoding="utf-8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
