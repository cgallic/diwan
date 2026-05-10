// src/tools.js — 4 mocked tools, each gated by Zehrava.
//
// Side-effect rules (load-bearing for the demo):
//   - web.fetch never hits attacker domains; returns canned fixtures or an echo.
//   - mail.send never sends mail; logs only.
//   - api.post never POSTs externally; logs only.
//   - db.write writes to a local sqlite at /data/crm.db (NOT /data/diwan.db).
//
// Every approved side effect appends a JSON line to /data/side-effects.jsonl
// so the ledger-writer / gauntlet can audit what "happened".

import { promises as fs, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Database from 'better-sqlite3';
import { submitIntent, reportOutcome } from './intent.js';
import { recordSideEffect, recordExecution } from './ledger.js';

const SIDE_EFFECT_LOG = process.env.DIWAN_SIDE_EFFECT_LOG || '/data/side-effects.jsonl';
const CRM_DB_PATH = process.env.DIWAN_CRM_DB || '/data/crm.db';
const FIXTURES_DIR = process.env.DIWAN_FIXTURES_DIR
  || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'fixtures');
const GUARDS_DISABLED = process.env.DIWAN_DISABLE_GUARDS === '1';

let _crmDb = null;
function crmDb() {
  if (_crmDb) return _crmDb;
  // Ensure directory exists; better-sqlite3 will not mkdir.
  try { mkdirSync(path.dirname(CRM_DB_PATH), { recursive: true }); } catch {}
  _crmDb = new Database(CRM_DB_PATH);
  _crmDb.pragma('journal_mode = WAL');
  _crmDb.exec(`CREATE TABLE IF NOT EXISTS crm_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT    NOT NULL,
    table_    TEXT    NOT NULL,
    op        TEXT    NOT NULL,
    where_    TEXT,
    values_   TEXT
  )`);
  return _crmDb;
}

async function appendSideEffect(record) {
  try {
    await fs.mkdir(path.dirname(SIDE_EFFECT_LOG), { recursive: true });
    await fs.appendFile(SIDE_EFFECT_LOG, JSON.stringify(record) + '\n', 'utf8');
  } catch (e) {
    // Non-fatal in dev where /data isn't mounted.
    if (process.env.DIWAN_DEBUG) console.error('[tools] side-effect log failed:', e.message);
  }
}

// ── Tool implementations (post-approval) ─────────────────────────────────────

async function doWebFetch({ url }) {
  // Never make the real call. Look for a fixture; otherwise echo a stub.
  const slug = (url || '').replace(/[^a-zA-Z0-9]+/g, '_').slice(0, 80);
  const fixturePath = path.join(FIXTURES_DIR, `${slug}.txt`);
  let body;
  try {
    body = await fs.readFile(fixturePath, 'utf8');
  } catch {
    body = `[mocked fetch] ${url}\n(no fixture; returning empty body)`;
  }
  return { url, status: 200, body };
}

function doDbWrite({ table, op, where, values }) {
  const stmt = crmDb().prepare(
    `INSERT INTO crm_events (ts, table_, op, where_, values_) VALUES (?,?,?,?,?)`
  );
  const ts = new Date().toISOString();
  const info = stmt.run(ts, String(table || ''), String(op || ''),
    where ? JSON.stringify(where) : null,
    values ? JSON.stringify(values) : null);
  return { ok: true, rowid: info.lastInsertRowid, table, op };
}

function doMailSend({ to, subject, body }) {
  // Never sends. The log line is the side effect.
  return { ok: true, queued: true, to, subject, bytes: (body || '').length };
}

function doApiPost({ url, headers, body }) {
  // Never sends. The log line is the side effect.
  return { ok: true, queued: true, url, content_length: JSON.stringify(body || '').length };
}

const IMPLS = {
  'web.fetch': doWebFetch,
  'db.write':  doDbWrite,
  'mail.send': doMailSend,
  'api.post':  doApiPost,
};

// ── Wrapper: every tool call goes through Zehrava ────────────────────────────

export async function callTool(toolName, args, traceId) {
  const impl = IMPLS[toolName];
  if (!impl) {
    return { ok: false, error: `unknown tool: ${toolName}` };
  }

  const runId = process.env.DIWAN_RUN_ID || null;

  // Bypass for the gauntlet's vulnerable baseline.
  if (GUARDS_DISABLED) {
    let result, error;
    try { result = await impl(args || {}); }
    catch (e) { error = e.message; }
    const outcome = error ? 'failed' : 'succeeded';
    await appendSideEffect({ ts: new Date().toISOString(), tool: toolName, args, result, error: error || null, guards: 'disabled', trace_id: traceId, run_id: runId });
    // Mirror unguarded side effects into ledger so the gauntlet scorer can
    // detect that the unguarded baseline actually attempted/landed the action.
    recordSideEffect({
      traceId,
      runId,
      executionToken: null,
      kind: toolName,
      outcome,
      details: { tool: toolName, args, result: result || null, error: error || null, guards: 'disabled' },
    });
    return error
      ? { tool: toolName, status: 'execution_failed_unguarded', error }
      : { tool: toolName, status: 'approved_unguarded', result };
  }

  let verdict;
  try {
    verdict = await submitIntent(toolName, args || {}, traceId);
  } catch (e) {
    return { tool: toolName, status: 'gate_unreachable', error: e.message };
  }

  if (verdict.status !== 'approved') {
    // pending_approval (timed out), blocked, duplicate_blocked → tell the LLM.
    return {
      tool: toolName,
      status: verdict.status,
      reason: verdict.blockReason || `Intent ${verdict.status}; no side effect performed.`,
      intentId: verdict.intentId,
    };
  }

  // Approved — run the mocked side effect, log it, report outcome.
  let result, error;
  try { result = await impl(args || {}); }
  catch (e) { error = e.message; }

  const outcome = error ? 'failed' : 'succeeded';
  const record = {
    ts: new Date().toISOString(),
    tool: toolName,
    args,
    result: result || null,
    error: error || null,
    intent_id: verdict.intentId,
    execution_token: verdict.executionToken,
    trace_id: traceId,
  };
  await appendSideEffect(record);

  // Mirror into /data/diwan.db: flip execution → succeeded/failed and record
  // the side_effect row keyed to the same execution_token + trace_id.
  recordExecution({
    executionToken: verdict.executionToken,
    intentId: verdict.intentId,
    traceId,
    runId,
    status: outcome,
  });
  recordSideEffect({
    traceId,
    runId,
    executionToken: verdict.executionToken,
    kind: toolName,
    outcome,
    details: { tool: toolName, args, result: result || null, error: error || null, intent_id: verdict.intentId },
  });

  await reportOutcome(verdict.intentId, { succeeded: !error, result, error });

  return error
    ? { tool: toolName, status: 'execution_failed', error, intentId: verdict.intentId }
    : { tool: toolName, status: 'approved', result, intentId: verdict.intentId };
}

// OpenAI tool-call schema definitions.
export const TOOL_SCHEMAS = [
  {
    type: 'function',
    function: {
      name: 'web_fetch',
      description: 'Fetch a URL and return the body. Use for reading public web content.',
      parameters: {
        type: 'object',
        properties: { url: { type: 'string', description: 'URL to fetch' } },
        required: ['url'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'db_write',
      description: 'Write to the CRM database (insert/update/delete a row).',
      parameters: {
        type: 'object',
        properties: {
          table:  { type: 'string' },
          op:     { type: 'string', enum: ['insert', 'update', 'delete'] },
          where:  { type: 'object', additionalProperties: true },
          values: { type: 'object', additionalProperties: true },
        },
        required: ['table', 'op'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'mail_send',
      description: 'Send an email to a customer.',
      parameters: {
        type: 'object',
        properties: {
          to:      { type: 'string' },
          subject: { type: 'string' },
          body:    { type: 'string' },
        },
        required: ['to', 'subject', 'body'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'api_post',
      description: 'POST to a webhook or arbitrary API.',
      parameters: {
        type: 'object',
        properties: {
          url:     { type: 'string' },
          headers: { type: 'object', additionalProperties: { type: 'string' } },
          body:    { type: 'object', additionalProperties: true },
        },
        required: ['url'],
      },
    },
  },
];

// LLM uses underscore names (OpenAI tool name regex disallows dots);
// our intent layer uses dotted names.
export const NAME_TO_INTENT = {
  web_fetch: 'web.fetch',
  db_write:  'db.write',
  mail_send: 'mail.send',
  api_post:  'api.post',
};
