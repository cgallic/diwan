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

    # verdict — Lobster Trap real schema has action/rule_name at top-level
    # (not nested under "verdict"). Also the 'side' field is called 'direction'.
    # Confirmed via T1.3 source-level read of veeainc/lobstertrap audit format.
    action = _first(event, "action") or _first(_get(event, "verdict") or {}, "action", "decision")
    if action:
        side = _first(event, "direction", "side", default="ingress")
        # Normalize ingress/egress vs old side= naming
        if side in ("inbound", "in"):
            side = "ingress"
        elif side in ("outbound", "out"):
            side = "egress"
        rule_name = _first(event, "rule_name", "rule") or _first(_get(event, "verdict") or {}, "rule_name", "rule")
        details_src = _first(event, "deny_message", "details", "reason") or _first(_get(event, "verdict") or {}, "details", "reason")
        rows.append((
            "verdict",
            {
                "trace_id": trace_id,
                "ts": ts,
                "run_id": run_id,
                "rule_name": rule_name,
                "action": str(action),
                "side": side,
                "details": _stringify(details_src) if details_src else None,
            },
        ))

    # Lobster Trap audit log doesn't carry prompt/response bodies — those rows
    # are written by agent-harness directly (it has the actual content). We
    # only derive verdict rows from Lobster's audit log.

    if not rows:
        log.warning("event produced 0 rows; keys=%s", list(event.keys())[:10])

    return rows
