CREATE TABLE prompt (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  run_id TEXT,                  -- non-null for gauntlet runs
  agent_name TEXT,
  body TEXT NOT NULL,           -- raw prompt JSON
  declared_intent TEXT          -- from _lobstertrap
);

CREATE TABLE response (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  run_id TEXT,
  body TEXT NOT NULL,
  detected_intent TEXT,
  risk_level TEXT,
  exfiltration_detected BOOLEAN
);

CREATE TABLE verdict (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  run_id TEXT,
  rule_name TEXT,
  action TEXT NOT NULL,         -- ALLOW | DENY | LOG | HUMAN_REVIEW | QUARANTINE | RATE_LIMIT
  side TEXT NOT NULL,           -- ingress | egress
  details TEXT
);

CREATE TABLE intent (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  intent_id TEXT UNIQUE NOT NULL,
  trace_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  run_id TEXT,
  agent_id TEXT,
  destination TEXT,
  payload TEXT,
  status TEXT,                  -- approved | pending_approval | blocked | duplicate_blocked
  policy_name TEXT,
  idempotency_key TEXT
);

CREATE TABLE execution (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  execution_token TEXT UNIQUE NOT NULL,
  intent_id TEXT NOT NULL,
  trace_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  run_id TEXT,
  status TEXT                   -- issued | succeeded | failed | expired
);

CREATE TABLE side_effect (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  run_id TEXT,
  execution_token TEXT,
  kind TEXT,                    -- db.write | mail.send | api.post | web.fetch
  outcome TEXT,                 -- succeeded | failed | none
  details TEXT
);

CREATE TABLE thought_summary (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  run_id TEXT,
  model TEXT,                   -- gemini-3.1-pro
  summary TEXT,
  violation_label TEXT          -- NIST AI RMF / OWASP LLM Top 10 tag
);

CREATE TABLE attack_run (
  run_id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  agent_name TEXT,
  total_attacks INTEGER,
  failed_count INTEGER,
  guarded BOOLEAN,
  notes TEXT
);

CREATE TABLE suggested_policy (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  attack_id TEXT,
  template_name TEXT,
  yaml_body TEXT,
  applied_in_run_id TEXT
);

CREATE INDEX idx_prompt_trace ON prompt(trace_id, ts);
CREATE INDEX idx_response_trace ON response(trace_id, ts);
CREATE INDEX idx_verdict_trace ON verdict(trace_id, ts);
CREATE INDEX idx_intent_trace ON intent(trace_id, ts);
CREATE INDEX idx_execution_trace ON execution(trace_id, ts);
CREATE INDEX idx_side_effect_trace ON side_effect(trace_id, ts);
CREATE INDEX idx_runs ON prompt(run_id) WHERE run_id IS NOT NULL;
