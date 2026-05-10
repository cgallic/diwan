// src/ledger.js — direct-write into /data/diwan.db.
//
// The ledger-writer service tails Lobster Trap's audit log and only emits
// prompt/response/verdict rows. Intent/execution/side_effect rows are not
// derived from any service log — Zehrava writes to its own /data/gate.db,
// and there is no "follow Zehrava events" tail in the ledger-writer (T2.3
// scope explicitly forbids editing ledger-writer). So the agent-harness
// double-writes those three event types directly into /data/diwan.db.
//
// This is the authoritative path for the demo. Schema must match
// ledger-writer/schema.sql — keep the two in sync if either changes.

import { mkdirSync } from 'node:fs';
import path from 'node:path';
import Database from 'better-sqlite3';

const LEDGER_PATH = process.env.LEDGER_PATH || '/data/diwan.db';

let _db = null;

function db() {
  if (_db) return _db;
  try { mkdirSync(path.dirname(LEDGER_PATH), { recursive: true }); } catch {}
  _db = new Database(LEDGER_PATH);
  _db.pragma('journal_mode = WAL');
  _db.pragma('synchronous = NORMAL');
  // Tables expected to already exist (ledger-writer creates them at startup);
  // if not, create them defensively so a stand-alone agent-harness still works.
  _db.exec(`
    CREATE TABLE IF NOT EXISTS intent (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      intent_id TEXT UNIQUE NOT NULL,
      trace_id TEXT NOT NULL,
      ts TEXT NOT NULL,
      run_id TEXT,
      agent_id TEXT,
      destination TEXT,
      payload TEXT,
      status TEXT,
      policy_name TEXT,
      idempotency_key TEXT
    );
    CREATE TABLE IF NOT EXISTS execution (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      execution_token TEXT UNIQUE NOT NULL,
      intent_id TEXT NOT NULL,
      trace_id TEXT NOT NULL,
      ts TEXT NOT NULL,
      run_id TEXT,
      status TEXT
    );
    CREATE TABLE IF NOT EXISTS side_effect (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      trace_id TEXT NOT NULL,
      ts TEXT NOT NULL,
      run_id TEXT,
      execution_token TEXT,
      kind TEXT,
      outcome TEXT,
      details TEXT
    );
  `);
  return _db;
}

export function recordIntent({ intentId, traceId, runId, agentId, destination, payload, status, policyName, idempotencyKey }) {
  try {
    db().prepare(`
      INSERT OR IGNORE INTO intent
        (intent_id, trace_id, ts, run_id, agent_id, destination, payload, status, policy_name, idempotency_key)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      intentId, traceId, new Date().toISOString(),
      runId || null, agentId || null, destination || null,
      payload != null ? (typeof payload === 'string' ? payload : JSON.stringify(payload)) : null,
      status || null, policyName || null, idempotencyKey || null
    );
  } catch (e) {
    if (process.env.DIWAN_DEBUG) console.error('[ledger] recordIntent failed:', e.message);
  }
}

export function recordExecution({ executionToken, intentId, traceId, runId, status }) {
  // Upsert by execution_token: first call from intent.js creates the row at
  // status='issued', the follow-up from tools.js promotes it to succeeded/failed.
  try {
    const conn = db();
    const existing = conn.prepare('SELECT id FROM execution WHERE execution_token = ?').get(executionToken);
    if (existing) {
      conn.prepare('UPDATE execution SET status = ?, ts = ? WHERE execution_token = ?')
        .run(status || 'issued', new Date().toISOString(), executionToken);
    } else {
      conn.prepare(`
        INSERT INTO execution
          (execution_token, intent_id, trace_id, ts, run_id, status)
        VALUES (?, ?, ?, ?, ?, ?)
      `).run(executionToken, intentId, traceId, new Date().toISOString(), runId || null, status || 'issued');
    }
  } catch (e) {
    if (process.env.DIWAN_DEBUG) console.error('[ledger] recordExecution failed:', e.message);
  }
}

export function recordSideEffect({ traceId, runId, executionToken, kind, outcome, details }) {
  try {
    db().prepare(`
      INSERT INTO side_effect
        (trace_id, ts, run_id, execution_token, kind, outcome, details)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      traceId, new Date().toISOString(), runId || null,
      executionToken || null, kind || null, outcome || null,
      details != null ? (typeof details === 'string' ? details : JSON.stringify(details)) : null
    );
  } catch (e) {
    if (process.env.DIWAN_DEBUG) console.error('[ledger] recordSideEffect failed:', e.message);
  }
}
