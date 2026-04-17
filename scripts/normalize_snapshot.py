#!/usr/bin/env python3
"""Normalize raw Kubernetes/OpenShift collection output into a compact JSON payload."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_top_nodes(text: str, limit: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        rest = parts[1:]
        cpu = rest[0] if len(rest) >= 1 else ""
        cpu_percent = None
        memory = None
        memory_percent = None
        # find percent tokens
        for token in rest[1:]:
            if token.endswith("%"):
                if cpu_percent is None:
                    cpu_percent = token
                else:
                    memory_percent = token
        # heuristic for memory tokens
        for token in reversed(rest):
            t = token.lower()
            if t.endswith("mi") or t.endswith("gi") or t.endswith("ki") or t.endswith("m") or t.endswith("g"):
                memory = token
                break
        results.append({"name": name, "cpu": cpu, "cpu_percent": cpu_percent, "memory": memory, "memory_percent": memory_percent})
    return results[:limit]


def parse_top_pods(text: str, limit: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        namespace = parts[0]
        name = parts[1] if len(parts) >= 2 else ""
        cpu = None
        memory = None
        if len(parts) >= 4:
            cpu = parts[2]
            memory = parts[3]
        elif len(parts) == 3:
            cpu = parts[2]
        results.append({"namespace": namespace, "name": name, "cpu": cpu, "memory": memory})
    return results[:limit]


def container_restart_count(pod: dict[str, Any]) -> int:
    total = 0
    for status in pod.get("status", {}).get("containerStatuses", []) or []:
        total += int(status.get("restartCount", 0) or 0)
    return total


def crashloop_like(pod: dict[str, Any]) -> bool:
    statuses = pod.get("status", {}).get("containerStatuses", []) or []
    for status in statuses:
        state = status.get("state", {}) or {}
        waiting = state.get("waiting") or {}
        reason = waiting.get("reason", "")
        if reason in {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError"}:
            return True
    return False


def node_ready(node: dict[str, Any]) -> bool:
    for condition in node.get("status", {}).get("conditions", []) or []:
        if condition.get("type") == "Ready":
            return condition.get("status") == "True"
    return False


def node_conditions(node: dict[str, Any]) -> list[str]:
    bad = []
    for condition in node.get("status", {}).get("conditions", []) or []:
        ctype = condition.get("type")
        cstatus = condition.get("status")
        if ctype != "Ready" and cstatus == "True":
            bad.append(ctype)
    return bad


def mask_name(value: str, redact: bool) -> str:
    if not value:
        return value
    return "<redacted>" if redact else value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-warning-events", type=int, default=40)
    parser.add_argument("--max-top-pods", type=int, default=25)
    parser.add_argument("--max-top-nodes", type=int, default=10)
    parser.add_argument("--max-namespaces", type=int, default=50)
    parser.add_argument("--max-restart-records", type=int, default=25)
    parser.add_argument("--redact-cluster-names", action="store_true", default=False)
    parser.add_argument("--redact-node-names", action="store_true", default=False)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_dir = Path(args.raw_dir)

    version = read_json(raw_dir / "version.json", {})
    nodes = read_json(raw_dir / "nodes.json", {"items": []}).get("items", [])
    namespaces = read_json(raw_dir / "namespaces.json", {"items": []}).get("items", [])
    pods = read_json(raw_dir / "pods.json", {"items": []}).get("items", [])
    events = read_json(raw_dir / "events.json", {"items": []}).get("items", [])
    clusteroperators = read_json(raw_dir / "clusteroperators.json", {"items": []}).get("items", [])
    top_nodes = parse_top_nodes(read_text(raw_dir / "top_nodes.txt"), args.max_top_nodes)
    top_pods = parse_top_pods(read_text(raw_dir / "top_pods.txt"), args.max_top_pods)

    ready_nodes = 0
    not_ready_nodes = 0
    node_summaries = []
    for node in nodes:
        ready = node_ready(node)
        if ready:
            ready_nodes += 1
        else:
            not_ready_nodes += 1
        node_name = node.get("metadata", {}).get("name")
        node_summaries.append(
            {
                "name": mask_name(node_name, args.redact_node_names),
                "ready": ready,
                "roles": [
                    key.replace("node-role.kubernetes.io/", "")
                    for key in (node.get("metadata", {}).get("labels", {}) or {}).keys()
                    if key.startswith("node-role.kubernetes.io/")
                ],
                "conditions": node_conditions(node),
            }
        )

    ns_counter: Counter[str] = Counter()
    pending_pods = 0
    crashloop_like_pods = 0
    total_restarts = 0
    restart_records = []
    pod_phase_counter: Counter[str] = Counter()

    for pod in pods:
        namespace = pod.get("metadata", {}).get("namespace", "unknown")
        name = pod.get("metadata", {}).get("name", "unknown")
        phase = pod.get("status", {}).get("phase", "Unknown")
        restarts = container_restart_count(pod)
        ns_counter[namespace] += 1
        pod_phase_counter[phase] += 1
        total_restarts += restarts

        if phase == "Pending":
            pending_pods += 1
        if crashloop_like(pod):
            crashloop_like_pods += 1
        if restarts > 0:
            restart_records.append(
                {
                    "namespace": namespace,
                    "name": mask_name(name, args.redact_node_names),
                    "phase": phase,
                    "restarts": restarts,
                }
            )

    restart_records.sort(key=lambda x: x["restarts"], reverse=True)

    namespace_summaries = [
        {"name": ns, "pod_count": count}
        for ns, count in ns_counter.most_common(args.max_namespaces)
    ]

    warning_events = []
    for event in events[: args.max_warning_events]:
        involved = event.get("involvedObject", {}) or {}
        warning_events.append(
            {
                "namespace": event.get("metadata", {}).get("namespace"),
                "reason": event.get("reason"),
                "kind": involved.get("kind"),
                "name": mask_name(involved.get("name"), args.redact_node_names),
                "message": event.get("message"),
                "lastTimestamp": event.get("lastTimestamp") or event.get("eventTime"),
            }
        )

    degraded_operators = []
    for op in clusteroperators:
        conditions = op.get("status", {}).get("conditions", []) or []
        degraded = [c for c in conditions if c.get("type") == "Degraded" and c.get("status") == "True"]
        unavailable = [c for c in conditions if c.get("type") == "Available" and c.get("status") != "True"]
        progressing = [c for c in conditions if c.get("type") == "Progressing" and c.get("status") == "True"]
        if degraded or unavailable or progressing:
            degraded_operators.append(
                {
                    "name": op.get("metadata", {}).get("name"),
                    "degraded": [c.get("message") for c in degraded],
                    "unavailable": [c.get("message") for c in unavailable],
                    "progressing": [c.get("message") for c in progressing],
                }
            )

    server_version = (
        version.get("serverVersion", {}).get("gitVersion")
        or version.get("serverVersion", {}).get("major")
        or "unknown"
    )

    

    signals: list[str] = []
    if not_ready_nodes:
        signals.append(f"{not_ready_nodes} node(s) are NotReady")
    if pending_pods:
        signals.append(f"{pending_pods} pod(s) are Pending")
    if crashloop_like_pods:
        signals.append(f"{crashloop_like_pods} pod(s) show CrashLoop/ImagePull-like issues")
    if total_restarts:
        signals.append(f"{total_restarts} total container restarts detected")
    if degraded_operators:
        signals.append(f"{len(degraded_operators)} OpenShift cluster operator(s) are degraded/unavailable/progressing")

    payload = {
        "cluster_name": mask_name(args.cluster_name, args.redact_cluster_names),
        "platform": args.platform,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "kubernetes": {
            "server_version": server_version,
        },
        "summary": {
            "total_nodes": len(nodes),
            "ready_nodes": ready_nodes,
            "not_ready_nodes": not_ready_nodes,
            "total_namespaces": len(namespaces),
            "total_pods": len(pods),
            "pending_pods": pending_pods,
            "crashloop_like_pods": crashloop_like_pods,
            "total_restarts": total_restarts,
            "pod_phases": dict(pod_phase_counter),
        },
        "top_nodes": [
            { **n, "name": mask_name(n.get("name"), args.redact_node_names) } for n in top_nodes
        ],
        "top_pods": [
            { **p, "name": mask_name(p.get("name"), args.redact_node_names) } for p in top_pods
        ],
        "nodes": node_summaries[: args.max_top_nodes],
        "namespaces": namespace_summaries,
        "restart_hotspots": restart_records[: args.max_restart_records],
        "warning_events": warning_events,
        "openshift_clusteroperators": degraded_operators,
        "signals": signals,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
