#!/usr/bin/env python3
"""Simple RAG retrieval from local runbooks using normalized snapshot signals.

This is a lightweight retrieval: it scans markdown files under a knowledge dir
and returns those that contain keywords derived from the `signals` in the
normalized payload. Outputs a JSON list with matched documents and snippets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, List, Dict


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--normalized", required=True)
    p.add_argument("--knowledge-dir", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def load_normalized(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def collect_runbooks(dirpath: Path) -> List[Path]:
    if not dirpath.exists():
        return []
    return list(dirpath.rglob("*.md"))


def match_documents(signals: List[str], docs: List[Path]) -> List[Dict[str, Any]]:
    matches = []
    low = [s.lower() for s in signals]
    for d in docs:
        txt = d.read_text(encoding="utf-8")
        tlow = txt.lower()
        score = 0
        for s in low:
            if s and s in tlow:
                score += 1
        if score > 0:
            snippet = txt[:1000]
            matches.append({"path": str(d), "score": score, "snippet": snippet})
    # sort by score desc
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches


def main() -> int:
    args = parse_args()
    norm = load_normalized(Path(args.normalized))
    signals = norm.get("signals", []) if isinstance(norm, dict) else []
    docs = collect_runbooks(Path(args.knowledge_dir))
    matches = match_documents(signals, docs)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(matches, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
