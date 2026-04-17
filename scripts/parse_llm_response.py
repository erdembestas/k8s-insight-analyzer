#!/usr/bin/env python3
"""Parse and validate LLM response content into a stable JSON with expected keys.

This helper is defensive: it accepts either the full LLM API JSON (choices[...] style)
or a direct assistant content which itself is JSON. It will emit a JSON object
with keys: general_health, critical_findings, risk_level, recommended_actions, missing_data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from jsonschema import validate, ValidationError

REQ_KEYS = ["general_health", "critical_findings", "risk_level", "recommended_actions", "missing_data"]

# Expected schema for the model's assistant JSON
LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "general_health": {"type": "string"},
        "critical_findings": {"type": "array"},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "recommended_actions": {"type": "array"},
        "missing_data": {"type": "array"},
    },
    "required": ["general_health", "critical_findings", "risk_level", "recommended_actions", "missing_data"],
}


def safe_load_json(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:
        # attempt to extract first {...} block
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(s[start : end + 1])
            except Exception:
                return None
        return None


def normalize(parsed: Any) -> dict:
    if not isinstance(parsed, dict):
        return {
            "general_health": "Unable to parse model response",
            "critical_findings": [],
            "risk_level": "medium",
            "recommended_actions": [],
            "missing_data": ["Response parsing failed"],
        }

    # If we got the standard OpenAI-like envelope, try to extract assistant content
    if "choices" in parsed and isinstance(parsed.get("choices"), list) and len(parsed["choices"]) > 0:
        choice = parsed["choices"][0]
        # Chat completions: choice.message.content
        content = None
        if isinstance(choice.get("message"), dict):
            content = choice.get("message", {}).get("content")
        if content is None and "text" in choice:
            content = choice.get("text")
        if content:
            inner = safe_load_json(content)
            if isinstance(inner, dict):
                parsed = inner

    # If parsed already contains the expected keys, use it, otherwise fill defaults
    result = {}
    result["general_health"] = parsed.get("general_health") or "No general_health provided"
    result["critical_findings"] = parsed.get("critical_findings") or []
    result["risk_level"] = parsed.get("risk_level") or "medium"
    result["recommended_actions"] = parsed.get("recommended_actions") or []
    result["missing_data"] = parsed.get("missing_data") or []
    # Ensure types
    if not isinstance(result["critical_findings"], list):
        result["critical_findings"] = [result["critical_findings"]]
    if not isinstance(result["recommended_actions"], list):
        result["recommended_actions"] = []
    if result["risk_level"] not in {"low", "medium", "high", "critical"}:
        # normalize or fallback
        result["risk_level"] = str(result["risk_level"]).lower() if result["risk_level"] else "medium"
        if result["risk_level"] not in {"low", "medium", "high", "critical"}:
            result["risk_level"] = "medium"
    # Validate against schema and record validation errors in missing_data
    try:
        validate(instance=result, schema=LLM_SCHEMA)
    except ValidationError as e:
        vd = f"schema_validation_error: {e.message}"
        if vd not in result["missing_data"]:
            result["missing_data"].append(vd)
    return result


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    inp = Path(args.input)
    out = Path(args.output)
    if not inp.exists():
        print(f"Input file {inp} not found")
        return 2
    text = inp.read_text(encoding="utf-8")
    parsed = safe_load_json(text)
    # If the raw file is an envelope with a 'body' string, try parsing that body
    if isinstance(parsed, dict) and isinstance(parsed.get("body"), str):
        inner = safe_load_json(parsed.get("body"))
        if isinstance(inner, dict):
            parsed = inner
    if parsed is None:
        # give generic fallback
        normalized = {
            "general_health": "Unable to parse model response",
            "critical_findings": [],
            "risk_level": "medium",
            "recommended_actions": [],
            "missing_data": ["Response parsing failed"],
        }
    else:
        normalized = normalize(parsed)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
