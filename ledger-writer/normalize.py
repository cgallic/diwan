"""Pure normalization: Lobster Trap audit event -> list of (table, row_dict) tuples.

Defensive: Lobster Trap's exact format is being verified in parallel (T1.3).
Handles common shapes; missing fields return None; unknown shapes degrade gracefully.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

log = logging.getLogger("ledger_writer.normalize")


def _get(d: Any, *keys: str, default: Any = None) -> Any:
    """Walk nested dict by keys; return default if any link is missing."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _first(d: dict, *keys: str, default: Any = None) -> Any:
    """Return first present key's value (top-level only)."""
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def _extract_trace_id(event: dict) -> str:
    """trace_id resolution order: trace_id, request_id, X-Trace-Id header. Else uuid4."""
    tid = _first(event, "trace_id", "request_id")
    if tid:
        return str(tid)
    # header lookup (case-insensitive on common spots)
    for path in (("headers",), ("request", "headers"), ("metadata", "headers")):
        hdrs = _get(event, *path)
        if isinstance(hdrs, dict):
            for hk, hv in hdrs.items():
                if hk.lower() == "x-trace-id" and hv:
                    return str(hv)
    new_id = str(uuid.uuid4())
    log.warning("event missing trace_id; generated %s", new_id)
    return new_id


def _lobstertrap_meta(event: dict) -> dict:
    """Extract _lobstertrap metadata block; tolerant of missing/partial."""
    meta = event.get("_lobstertrap") or {}
    if not isinstance(meta, dict):
        return {}
    return {
        "declared_intent": meta.get("declared_intent"),
        "detected_intent": meta.get("detected_intent"),
        "risk_level": meta.get("risk_level"),
        "exfiltration_detected": meta.get("exfiltration_detected"),
    }


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, default=str)
    except (TypeError, ValueError):
        return str(v)


def normalize(event: dict) -> list[tuple[str, dict]]:
    """Map a Lobster Trap audit event onto rows in our schema.

    Returns list of (table_name, row_dict) tuples.
    """
    if not isinstance(event, dict):
        log.warning("non-dict event ignored: %r", type(event).__name__)
        return []

    rows: list[tuple[str, dict]] = []
    ts = _first(event, "ts", "timestamp", "time", default="")
    trace_id = _extract_trace_id(event)
    run_id = _first(event, "run_id", "attack_run_id")
    agent_name = _first(event, "agent_name", "agent")
    meta = _lobstertrap_meta(event)

    # prompt: request OR prompt field present
    prompt_body = _first(event, "request", "prompt")
    if prompt_body is not None:
        rows.append((
            "prompt",
            {
                "trace_id": trace_id,
                "ts": ts,
                "run_id": run_id,
                "agent_name": agent_name,
                "body": _stringify(prompt_body),
                "declared_intent": meta.get("declared_intent"),
            },
        ))

    # response
    response_body = _first(event, "response", "completion")
    if response_body is not None:
        exf = meta.get("exfiltration_detected")
        rows.append((
            "response",
            {
                "trace_id": trace_id,
                "ts": ts,
                "run_id": run_id,
                "body": _stringify(response_body),
                "detected_intent": meta.get("detected_intent"),
                "risk_level": meta.get("risk_level"),
                "exfiltration_detected": int(bool(exf)) if exf is not None else None,
            },
        ))

    # verdict — every event has one in normal flow, but be tolerant if absent
    verdict = event.get("verdict")
    if isinstance(verdict, dict):
        action = _first(verdict, "action", "decision")
        if action:  # action is NOT NULL in schema; skip if missing
            rows.append((
                "verdict",
                {
                    "trace_id": trace_id,
                    "ts": ts,
                    "run_id": run_id,
                    "rule_name": _first(verdict, "rule_name", "rule"),
                    "action": str(action),
                    "side": _first(event, "side", default=_first(verdict, "side", default="ingress")),
                    "details": _stringify(_first(verdict, "details", "reason", default=None)) or None,
                },
            ))
        else:
            log.warning("verdict block missing 'action' for trace %s", trace_id)

    if not rows:
        log.warning("event produced 0 rows; keys=%s", list(event.keys())[:10])

    return rows
