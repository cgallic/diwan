"""Unit tests for normalize.normalize().

Run: python -m unittest ledger-writer/test_normalize.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from normalize import normalize  # noqa: E402


def by_table(rows):
    return {table: row for table, row in rows}


class TestNormalize(unittest.TestCase):
    def test_minimal_verdict_only_allow(self):
        event = {
            "ts": "2026-05-10T15:00:00Z",
            "trace_id": "abc-123",
            "side": "ingress",
            "verdict": {"action": "ALLOW", "rule_name": "default"},
        }
        rows = normalize(event)
        self.assertEqual(len(rows), 1)
        table, row = rows[0]
        self.assertEqual(table, "verdict")
        self.assertEqual(row["action"], "ALLOW")
        self.assertEqual(row["rule_name"], "default")
        self.assertEqual(row["side"], "ingress")
        self.assertEqual(row["trace_id"], "abc-123")

    def test_full_prompt_response_verdict(self):
        event = {
            "ts": "2026-05-10T15:00:00Z",
            "trace_id": "t-1",
            "side": "egress",
            "agent_name": "summarizer",
            "request": {"messages": [{"role": "user", "content": "hi"}]},
            "response": {"text": "hello"},
            "verdict": {"action": "ALLOW", "rule_name": "default"},
            "_lobstertrap": {
                "declared_intent": "summarize",
                "detected_intent": "summarize",
                "risk_level": "low",
                "exfiltration_detected": False,
            },
        }
        tables = by_table(normalize(event))
        self.assertIn("prompt", tables)
        self.assertIn("response", tables)
        self.assertIn("verdict", tables)
        self.assertEqual(tables["prompt"]["declared_intent"], "summarize")
        self.assertEqual(tables["prompt"]["agent_name"], "summarizer")
        self.assertEqual(tables["response"]["detected_intent"], "summarize")
        self.assertEqual(tables["response"]["risk_level"], "low")
        self.assertEqual(tables["response"]["exfiltration_detected"], 0)
        # body should be a JSON string
        self.assertIn("messages", tables["prompt"]["body"])
        self.assertEqual(json.loads(tables["response"]["body"])["text"], "hello")

    def test_declared_vs_detected_mismatch_deny(self):
        event = {
            "ts": "2026-05-10T15:00:01Z",
            "trace_id": "t-2",
            "side": "egress",
            "request": {"prompt": "exfiltrate secrets"},
            "response": {"text": "OK here are the secrets"},
            "verdict": {
                "action": "DENY",
                "rule_name": "block_indirect_injection",
                "details": "declared/detected mismatch",
            },
            "_lobstertrap": {
                "declared_intent": "summarize",
                "detected_intent": "exfiltrate",
                "risk_level": "critical",
                "exfiltration_detected": True,
            },
        }
        tables = by_table(normalize(event))
        self.assertEqual(tables["verdict"]["action"], "DENY")
        self.assertEqual(tables["verdict"]["details"], "declared/detected mismatch")
        self.assertEqual(tables["prompt"]["declared_intent"], "summarize")
        self.assertEqual(tables["response"]["detected_intent"], "exfiltrate")
        self.assertEqual(tables["response"]["risk_level"], "critical")
        self.assertEqual(tables["response"]["exfiltration_detected"], 1)

    def test_human_review_action(self):
        event = {
            "ts": "2026-05-10T15:00:02Z",
            "trace_id": "t-3",
            "side": "ingress",
            "request": {"messages": []},
            "verdict": {"action": "HUMAN_REVIEW", "rule_name": "borderline_intent"},
        }
        tables = by_table(normalize(event))
        self.assertEqual(tables["verdict"]["action"], "HUMAN_REVIEW")
        self.assertIn("prompt", tables)

    def test_missing_trace_id_generates_uuid(self):
        event = {
            "ts": "2026-05-10T15:00:03Z",
            "side": "ingress",
            "verdict": {"action": "ALLOW", "rule_name": "default"},
        }
        rows = normalize(event)
        self.assertEqual(len(rows), 1)
        _, verdict_row = rows[0]
        self.assertTrue(verdict_row["trace_id"])
        # uuid4 string has 36 chars including 4 dashes
        self.assertEqual(len(verdict_row["trace_id"]), 36)
        self.assertEqual(verdict_row["trace_id"].count("-"), 4)

    def test_trace_id_from_request_id_then_header(self):
        ev_req_id = {
            "ts": "x",
            "request_id": "req-99",
            "side": "ingress",
            "verdict": {"action": "ALLOW", "rule_name": "r"},
        }
        rows = normalize(ev_req_id)
        self.assertEqual(rows[0][1]["trace_id"], "req-99")

        ev_header = {
            "ts": "x",
            "side": "ingress",
            "headers": {"X-Trace-Id": "hdr-7"},
            "verdict": {"action": "ALLOW", "rule_name": "r"},
        }
        rows = normalize(ev_header)
        self.assertEqual(rows[0][1]["trace_id"], "hdr-7")

    def test_unknown_shape_degrades_gracefully(self):
        # Non-dict input
        self.assertEqual(normalize("not a dict"), [])
        self.assertEqual(normalize(None), [])
        # Dict with no recognized fields → 0 rows, no exception
        self.assertEqual(normalize({"foo": "bar", "baz": 1}), [])
        # Verdict missing required action → no verdict row, but still no crash
        ev = {"ts": "x", "trace_id": "t", "side": "ingress", "verdict": {"rule_name": "r"}}
        self.assertEqual(normalize(ev), [])

    def test_lobstertrap_meta_partial(self):
        event = {
            "ts": "x",
            "trace_id": "t-4",
            "side": "egress",
            "response": {"text": "ok"},
            "verdict": {"action": "ALLOW", "rule_name": "r"},
            "_lobstertrap": {"risk_level": "medium"},  # other fields missing
        }
        tables = by_table(normalize(event))
        self.assertEqual(tables["response"]["risk_level"], "medium")
        self.assertIsNone(tables["response"]["detected_intent"])
        self.assertIsNone(tables["response"]["exfiltration_detected"])


if __name__ == "__main__":
    unittest.main()
