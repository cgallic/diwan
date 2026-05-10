-- views.sql — derived read-only views over the diwan ledger.
--
-- Idempotency strategy: DROP VIEW IF EXISTS + CREATE VIEW.
-- Why not CREATE VIEW IF NOT EXISTS? Because we want startup to pick up the
-- LATEST definition of these views even when the schema/views file changes
-- between deploys; tables (heavy, contain data) are gated behind the probe in
-- ledger_writer.init_db, but views are cheap derivations and should always
-- match the file on disk.
--
-- CAVEAT (flag for D3): "denied" here treats both Lobster Trap verdict
-- DENY and Zehrava intent.status='blocked' as denial. Zehrava intent has
-- 4 statuses (approved | pending_approval | blocked | duplicate_blocked).
-- Today we count ONLY 'blocked' as denied; 'duplicate_blocked' is treated as
-- a soft-block (idempotency, not policy) and excluded. If D3 wants
-- duplicate_blocked counted as denial, change the trace_summary.denied
-- predicate and attack_run_summary.blocked_count CTE.

DROP VIEW IF EXISTS trace_summary;
CREATE VIEW trace_summary AS
WITH all_events AS (
    SELECT trace_id, ts FROM prompt
    UNION ALL SELECT trace_id, ts FROM response
    UNION ALL SELECT trace_id, ts FROM verdict
    UNION ALL SELECT trace_id, ts FROM intent
    UNION ALL SELECT trace_id, ts FROM execution
    UNION ALL SELECT trace_id, ts FROM side_effect
),
agg_events AS (
    SELECT trace_id, MIN(ts) AS first_ts, MAX(ts) AS last_ts
    FROM all_events
    GROUP BY trace_id
),
agent AS (
    -- A trace may have multiple prompts; pick the earliest non-null agent_name.
    SELECT trace_id, agent_name
    FROM (
        SELECT trace_id, agent_name,
               ROW_NUMBER() OVER (PARTITION BY trace_id ORDER BY ts ASC, id ASC) AS rn
        FROM prompt
        WHERE agent_name IS NOT NULL
    )
    WHERE rn = 1
),
counts AS (
    SELECT t.trace_id,
           (SELECT COUNT(*) FROM prompt      WHERE prompt.trace_id      = t.trace_id) AS prompt_count,
           (SELECT COUNT(*) FROM response    WHERE response.trace_id    = t.trace_id) AS response_count,
           (SELECT COUNT(*) FROM verdict     WHERE verdict.trace_id     = t.trace_id) AS verdict_count,
           (SELECT COUNT(*) FROM intent      WHERE intent.trace_id      = t.trace_id) AS intent_count,
           (SELECT COUNT(*) FROM execution   WHERE execution.trace_id   = t.trace_id) AS execution_count,
           (SELECT COUNT(*) FROM side_effect WHERE side_effect.trace_id = t.trace_id) AS side_effect_count
    FROM agg_events t
),
flags AS (
    SELECT t.trace_id,
           -- denied: any DENY verdict OR any blocked intent
           CASE WHEN
                EXISTS (SELECT 1 FROM verdict v WHERE v.trace_id = t.trace_id AND v.action = 'DENY')
                OR EXISTS (SELECT 1 FROM intent i WHERE i.trace_id = t.trace_id AND i.status = 'blocked')
           THEN 1 ELSE 0 END AS denied,
           -- human_review_pending: a HUMAN_REVIEW verdict exists AND no execution
           -- token has been issued for any intent on this trace. We use trace-scope
           -- (not per-intent) because verdicts don't carry intent_id.
           CASE WHEN
                EXISTS (SELECT 1 FROM verdict v WHERE v.trace_id = t.trace_id AND v.action = 'HUMAN_REVIEW')
                AND NOT EXISTS (
                    SELECT 1 FROM execution e
                    JOIN intent i ON i.intent_id = e.intent_id
                    WHERE i.trace_id = t.trace_id
                )
           THEN 1 ELSE 0 END AS human_review_pending
    FROM agg_events t
)
SELECT
    e.trace_id,
    e.first_ts,
    e.last_ts,
    a.agent_name,
    c.prompt_count,
    c.response_count,
    c.verdict_count,
    c.intent_count,
    c.execution_count,
    c.side_effect_count,
    f.denied,
    f.human_review_pending,
    -- final_status: 'denied' if any DENY/blocked, else 'pending_review' if any
    -- HUMAN_REVIEW awaiting execution, else 'allowed' if at least one ALLOW
    -- verdict exists with no denial/review, else 'mixed' (e.g., LOG-only,
    -- unresolved combinations).
    CASE
        WHEN f.denied = 1 THEN 'denied'
        WHEN f.human_review_pending = 1 THEN 'pending_review'
        WHEN EXISTS (SELECT 1 FROM verdict v WHERE v.trace_id = e.trace_id AND v.action = 'ALLOW')
             AND NOT EXISTS (SELECT 1 FROM verdict v WHERE v.trace_id = e.trace_id AND v.action IN ('DENY', 'HUMAN_REVIEW'))
            THEN 'allowed'
        ELSE 'mixed'
    END AS final_status
FROM agg_events e
LEFT JOIN agent  a ON a.trace_id = e.trace_id
LEFT JOIN counts c ON c.trace_id = e.trace_id
LEFT JOIN flags  f ON f.trace_id = e.trace_id;


DROP VIEW IF EXISTS attack_run_summary;
CREATE VIEW attack_run_summary AS
WITH run_traces AS (
    -- Every distinct (run_id, trace_id) pair we've seen across the ledger.
    -- A run's trace can be referenced from any event table; we union-distinct
    -- so we don't undercount when, say, a prompt was logged but the verdict
    -- wasn't (or vice versa).
    SELECT run_id, trace_id FROM prompt      WHERE run_id IS NOT NULL
    UNION SELECT run_id, trace_id FROM response    WHERE run_id IS NOT NULL
    UNION SELECT run_id, trace_id FROM verdict     WHERE run_id IS NOT NULL
    UNION SELECT run_id, trace_id FROM intent      WHERE run_id IS NOT NULL
    UNION SELECT run_id, trace_id FROM execution   WHERE run_id IS NOT NULL
    UNION SELECT run_id, trace_id FROM side_effect WHERE run_id IS NOT NULL
),
trace_flags AS (
    -- Per (run_id, trace_id): did Lobster or Zehrava block it? Was it
    -- HUMAN_REVIEW pending? Reuses trace_summary's logic but scoped to
    -- the run for the join.
    SELECT
        rt.run_id,
        rt.trace_id,
        ts.denied,
        ts.human_review_pending
    FROM run_traces rt
    LEFT JOIN trace_summary ts ON ts.trace_id = rt.trace_id
)
SELECT
    ar.run_id,
    ar.ts,
    ar.agent_name,
    COUNT(DISTINCT tf.trace_id)                                            AS total_attacks,
    -- failed_count: attacks that "got through" — were NOT denied and NOT
    -- pending review. The expectation in a gauntlet run is the guard
    -- catches the attack; if it didn't, that's a guard failure.
    SUM(CASE WHEN COALESCE(tf.denied, 0) = 0
                  AND COALESCE(tf.human_review_pending, 0) = 0
             THEN 1 ELSE 0 END)                                            AS failed_count,
    SUM(COALESCE(tf.denied, 0))                                            AS blocked_count,
    SUM(COALESCE(tf.human_review_pending, 0))                              AS human_review_count,
    -- risk_pct: % of attacks blocked. Cast to REAL so we don't get integer
    -- division. NULL-safe: if total_attacks is 0, returns NULL.
    CASE WHEN COUNT(DISTINCT tf.trace_id) = 0 THEN NULL
         ELSE SUM(COALESCE(tf.denied, 0)) * 100.0 / COUNT(DISTINCT tf.trace_id)
    END                                                                    AS risk_pct
FROM attack_run ar
LEFT JOIN trace_flags tf ON tf.run_id = ar.run_id
GROUP BY ar.run_id, ar.ts, ar.agent_name;
