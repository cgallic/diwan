"""Unit tests for views.sql (trace_summary, attack_run_summary).

Run: python -m unittest ledger-writer/test_views.py

Strategy: build an in-memory SQLite, load schema.sql + views.sql, hand-insert
representative rows across one ad-hoc trace and two attack runs, then assert
that the views aggregate correctly.
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript((HERE / "schema.sql").read_text())
    conn.executescript((HERE / "views.sql").read_text())
    return conn


def insert(conn: sqlite3.Connection, table: str, **row) -> None:
    cols = ",".join(row.keys())
    placeholders = ",".join(["?"] * len(row))
    conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        list(row.values()),
    )


class TestViews(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = fresh_db()
        self._seed()
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _seed(self) -> None:
        c = self.conn

        # ---------- ad-hoc trace (no run_id): 5 events ----------
        # 1 prompt, 1 response, 1 verdict (ALLOW), 1 intent (approved),
        # 1 execution (issued).
        insert(c, "prompt",
               trace_id="adhoc-1", ts="2026-05-09T10:00:00Z",
               agent_name="summarizer", body='{"prompt":"hi"}',
               declared_intent="summarize")
        insert(c, "response",
               trace_id="adhoc-1", ts="2026-05-09T10:00:01Z",
               body='{"text":"hello"}', detected_intent="summarize",
               risk_level="low", exfiltration_detected=0)
        insert(c, "verdict",
               trace_id="adhoc-1", ts="2026-05-09T10:00:02Z",
               rule_name="default", action="ALLOW", side="egress")
        insert(c, "intent",
               intent_id="int-adhoc-1", trace_id="adhoc-1",
               ts="2026-05-09T10:00:03Z", agent_id="summarizer",
               destination="db", payload="{}", status="approved",
               policy_name="default", idempotency_key="k1")
        insert(c, "execution",
               execution_token="tok-adhoc-1", intent_id="int-adhoc-1",
               trace_id="adhoc-1", ts="2026-05-09T10:00:04Z", status="issued")

        # ---------- gauntlet run-A: 3 traces ----------
        insert(c, "attack_run", run_id="run-A", ts="2026-05-09T11:00:00Z",
               agent_name="victim-a", total_attacks=3, failed_count=0,
               guarded=1, notes="")

        # run-A trace 1: blocked by Lobster (verdict DENY)
        insert(c, "prompt", trace_id="A-t1", ts="2026-05-09T11:00:01Z",
               run_id="run-A", agent_name="victim-a",
               body='{"p":"exfiltrate"}', declared_intent="summarize")
        insert(c, "verdict", trace_id="A-t1", ts="2026-05-09T11:00:02Z",
               run_id="run-A", rule_name="block_exfil",
               action="DENY", side="egress", details="mismatch")

        # run-A trace 2: blocked by Zehrava (intent.status='blocked')
        insert(c, "prompt", trace_id="A-t2", ts="2026-05-09T11:00:03Z",
               run_id="run-A", agent_name="victim-a",
               body='{"p":"call api"}', declared_intent="api_call")
        insert(c, "verdict", trace_id="A-t2", ts="2026-05-09T11:00:04Z",
               run_id="run-A", rule_name="default",
               action="ALLOW", side="ingress")
        insert(c, "intent", intent_id="int-A-t2", trace_id="A-t2",
               ts="2026-05-09T11:00:05Z", run_id="run-A",
               agent_id="victim-a", destination="api.evil.com",
               payload="{}", status="blocked",
               policy_name="egress_allowlist", idempotency_key="k-A-t2")

        # run-A trace 3: attack got through — ALLOW + approved intent + execution
        insert(c, "prompt", trace_id="A-t3", ts="2026-05-09T11:00:06Z",
               run_id="run-A", agent_name="victim-a",
               body='{"p":"benign"}', declared_intent="summarize")
        insert(c, "verdict", trace_id="A-t3", ts="2026-05-09T11:00:07Z",
               run_id="run-A", rule_name="default",
               action="ALLOW", side="egress")
        insert(c, "intent", intent_id="int-A-t3", trace_id="A-t3",
               ts="2026-05-09T11:00:08Z", run_id="run-A",
               agent_id="victim-a", destination="db", payload="{}",
               status="approved", policy_name="default",
               idempotency_key="k-A-t3")
        insert(c, "execution", execution_token="tok-A-t3",
               intent_id="int-A-t3", trace_id="A-t3",
               ts="2026-05-09T11:00:09Z", run_id="run-A", status="issued")

        # ---------- gauntlet run-B: 3 traces ----------
        insert(c, "attack_run", run_id="run-B", ts="2026-05-09T12:00:00Z",
               agent_name="victim-b", total_attacks=3, failed_count=0,
               guarded=1, notes="")

        # run-B trace 1: HUMAN_REVIEW pending (no execution issued)
        insert(c, "prompt", trace_id="B-t1", ts="2026-05-09T12:00:01Z",
               run_id="run-B", agent_name="victim-b",
               body='{"p":"borderline"}', declared_intent="?")
        insert(c, "verdict", trace_id="B-t1", ts="2026-05-09T12:00:02Z",
               run_id="run-B", rule_name="borderline_intent",
               action="HUMAN_REVIEW", side="ingress")

        # run-B trace 2: HUMAN_REVIEW resolved (execution token issued -> not pending)
        insert(c, "prompt", trace_id="B-t2", ts="2026-05-09T12:00:03Z",
               run_id="run-B", agent_name="victim-b",
               body='{"p":"borderline2"}', declared_intent="?")
        insert(c, "verdict", trace_id="B-t2", ts="2026-05-09T12:00:04Z",
               run_id="run-B", rule_name="borderline_intent",
               action="HUMAN_REVIEW", side="ingress")
        insert(c, "intent", intent_id="int-B-t2", trace_id="B-t2",
               ts="2026-05-09T12:00:05Z", run_id="run-B",
               agent_id="victim-b", destination="db", payload="{}",
               status="approved", policy_name="default",
               idempotency_key="k-B-t2")
        insert(c, "execution", execution_token="tok-B-t2",
               intent_id="int-B-t2", trace_id="B-t2",
               ts="2026-05-09T12:00:06Z", run_id="run-B", status="issued")

        # run-B trace 3: clean ALLOW
        insert(c, "prompt", trace_id="B-t3", ts="2026-05-09T12:00:07Z",
               run_id="run-B", agent_name="victim-b",
               body='{"p":"hello"}', declared_intent="summarize")
        insert(c, "verdict", trace_id="B-t3", ts="2026-05-09T12:00:08Z",
               run_id="run-B", rule_name="default",
               action="ALLOW", side="egress")

    # ------------------------------------------------------------------
    # trace_summary
    # ------------------------------------------------------------------
    def test_trace_summary_row_count(self):
        rows = list(self.conn.execute("SELECT trace_id FROM trace_summary"))
        # 1 ad-hoc + 3 run-A + 3 run-B = 7 unique traces
        self.assertEqual(len(rows), 7)

    def test_trace_summary_adhoc_counts(self):
        row = self.conn.execute(
            "SELECT * FROM trace_summary WHERE trace_id = 'adhoc-1'"
        ).fetchone()
        self.assertEqual(row["agent_name"], "summarizer")
        self.assertEqual(row["prompt_count"], 1)
        self.assertEqual(row["response_count"], 1)
        self.assertEqual(row["verdict_count"], 1)
        self.assertEqual(row["intent_count"], 1)
        self.assertEqual(row["execution_count"], 1)
        self.assertEqual(row["side_effect_count"], 0)
        self.assertEqual(row["denied"], 0)
        self.assertEqual(row["human_review_pending"], 0)
        self.assertEqual(row["final_status"], "allowed")
        self.assertEqual(row["first_ts"], "2026-05-09T10:00:00Z")
        self.assertEqual(row["last_ts"], "2026-05-09T10:00:04Z")

    def test_trace_summary_lobster_deny(self):
        row = self.conn.execute(
            "SELECT * FROM trace_summary WHERE trace_id = 'A-t1'"
        ).fetchone()
        self.assertEqual(row["denied"], 1)
        self.assertEqual(row["human_review_pending"], 0)
        self.assertEqual(row["final_status"], "denied")

    def test_trace_summary_zehrava_blocked(self):
        row = self.conn.execute(
            "SELECT * FROM trace_summary WHERE trace_id = 'A-t2'"
        ).fetchone()
        # Verdict was ALLOW but Zehrava intent was 'blocked'
        self.assertEqual(row["denied"], 1)
        self.assertEqual(row["final_status"], "denied")

    def test_trace_summary_attack_got_through(self):
        row = self.conn.execute(
            "SELECT * FROM trace_summary WHERE trace_id = 'A-t3'"
        ).fetchone()
        self.assertEqual(row["denied"], 0)
        self.assertEqual(row["human_review_pending"], 0)
        self.assertEqual(row["final_status"], "allowed")
        self.assertEqual(row["execution_count"], 1)

    def test_trace_summary_human_review_pending(self):
        row = self.conn.execute(
            "SELECT * FROM trace_summary WHERE trace_id = 'B-t1'"
        ).fetchone()
        self.assertEqual(row["denied"], 0)
        self.assertEqual(row["human_review_pending"], 1)
        self.assertEqual(row["final_status"], "pending_review")

    def test_trace_summary_human_review_resolved(self):
        row = self.conn.execute(
            "SELECT * FROM trace_summary WHERE trace_id = 'B-t2'"
        ).fetchone()
        # HUMAN_REVIEW verdict but execution token was issued => no longer pending
        self.assertEqual(row["human_review_pending"], 0)
        # Not denied, not pending — so final_status falls through. Has both
        # ALLOW (none, only HUMAN_REVIEW) so this becomes 'mixed'.
        self.assertEqual(row["final_status"], "mixed")

    # ------------------------------------------------------------------
    # attack_run_summary
    # ------------------------------------------------------------------
    def test_attack_run_summary_row_count(self):
        rows = list(self.conn.execute("SELECT run_id FROM attack_run_summary"))
        self.assertEqual(len(rows), 2)

    def test_attack_run_summary_run_A(self):
        row = self.conn.execute(
            "SELECT * FROM attack_run_summary WHERE run_id = 'run-A'"
        ).fetchone()
        self.assertEqual(row["agent_name"], "victim-a")
        self.assertEqual(row["total_attacks"], 3)
        self.assertEqual(row["blocked_count"], 2)        # A-t1 (DENY) + A-t2 (intent blocked)
        self.assertEqual(row["failed_count"], 1)         # A-t3 got through
        self.assertEqual(row["human_review_count"], 0)
        # 2/3 = 66.666...
        self.assertAlmostEqual(row["risk_pct"], 200.0 / 3.0, places=4)

    def test_attack_run_summary_run_B(self):
        row = self.conn.execute(
            "SELECT * FROM attack_run_summary WHERE run_id = 'run-B'"
        ).fetchone()
        self.assertEqual(row["agent_name"], "victim-b")
        self.assertEqual(row["total_attacks"], 3)
        self.assertEqual(row["blocked_count"], 0)
        self.assertEqual(row["human_review_count"], 1)   # only B-t1
        # B-t2 (resolved review) and B-t3 (clean ALLOW) both got through
        self.assertEqual(row["failed_count"], 2)
        self.assertAlmostEqual(row["risk_pct"], 0.0, places=4)

    # ------------------------------------------------------------------
    # idempotency: re-running views.sql should not break anything
    # ------------------------------------------------------------------
    def test_views_sql_idempotent(self):
        views_sql = (HERE / "views.sql").read_text()
        # Re-apply twice; should not raise and counts should be unchanged.
        self.conn.executescript(views_sql)
        self.conn.executescript(views_sql)
        rows = list(self.conn.execute("SELECT trace_id FROM trace_summary"))
        self.assertEqual(len(rows), 7)


if __name__ == "__main__":
    unittest.main()
