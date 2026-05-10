# ledger-writer component

**What**: NEW service. Tails Lobster Trap's audit log (JSONL on disk), normalizes each event into our SQLite schema, inserts with WAL. Critical because Lobster Trap doesn't natively write to our schema.

## Inputs

- Audit log path (env `LOBSTERTRAP_AUDIT_LOG=/data/lobstertrap-audit.log`)
- Ledger path (env `LEDGER_PATH=/data/diwan.db`)

## Outputs

- SQLite ledger at `/data/diwan.db` populated with `prompt`, `response`, `verdict` rows tagged with `trace_id`
- (Zehrava writes its own `intent`/`execution`/`side_effect` rows directly — ledger-writer doesn't touch those)

## Tasks owned

- **T1.1** — schema design (`schema.sql`)
- **T1.2** — Python service (~150 LoC)

## Schema (T1.1)

Write `ledger-writer/schema.sql`. Tables:

```sql
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
```

## Service (T1.2)

`ledger-writer/ledger_writer.py`:

```python
# Pseudocode skeleton
import sqlite3, json, os, time

DB = os.environ['LEDGER_PATH']
LOG = os.environ['LOBSTERTRAP_AUDIT_LOG']

def init_db(conn):
    with open('schema.sql') as f:
        conn.executescript(f.read())

def normalize(event):
    # Lobster Trap audit format → our schema
    # Returns list of (table, row_dict) tuples
    ...

def main():
    conn = sqlite3.connect(DB)
    conn.execute('PRAGMA journal_mode=WAL;')
    init_db(conn)

    with open(LOG, 'r') as f:
        f.seek(0, 2)  # seek to end
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            try:
                event = json.loads(line)
                for table, row in normalize(event):
                    cols = ','.join(row.keys())
                    placeholders = ','.join(['?'] * len(row))
                    conn.execute(f'INSERT INTO {table} ({cols}) VALUES ({placeholders})', list(row.values()))
                conn.commit()
            except Exception as e:
                print(f'normalize error: {e}', flush=True)

if __name__ == '__main__':
    main()
```

## Acceptance criteria

- `docker compose build ledger-writer` succeeds
- `docker compose up` brings ledger-writer up; it survives Lobster Trap not yet having written any audit lines
- After one prompt → response cycle through Lobster Trap, three rows appear in the SQLite ledger (one each in `prompt`, `response`, `verdict`)
- All three share the same `trace_id`
- `sqlite3 /data/diwan.db ".schema"` shows the 9 tables

## Fallback if blocked

- **Lobster Trap audit log isn't JSONL**: read upstream docs / source for the actual format. If it's binary or pluggable, configure a JSONL sink.
- **trace_id isn't in Lobster Trap output**: derive from request ID, or have agent-harness inject `X-Trace-Id` header that Lobster forwards.

## Reference docs

- Lobster Trap audit format: read upstream `internal/audit/` source
- SQLite WAL mode: stable for concurrent writers at our scale; no migration needed
