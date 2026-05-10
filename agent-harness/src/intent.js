// src/intent.js — Zehrava /v1/intents client with first-run agent registration.
//
// Flow:
//   1. On first call, POST /v1/agents/register {name, riskTier} → cache apiKey.
//      (Zehrava registration is unauthenticated by design; the apiKey it returns
//       is a fresh gate_sk_* token bound to the new agent row.)
//   2. POST /v1/intents with Authorization: Bearer <apiKey>.
//   3. If pending_approval, poll /v1/intents/:id until terminal or timeout.
//   4. Mirror the intent + execution into /data/diwan.db so the demo ledger
//      shows the full causal chain (the ledger-writer service does not tail
//      Zehrava — it only normalizes Lobster Trap).
//
// Tool→policy mapping: Zehrava's bundled policies (support-reply, crm-low-risk,
// internal-publish) define destination allowlists. We translate each agent
// tool to a (policy, destination) pair Zehrava recognizes; the actual
// side-effect logged in our ledger keeps the dotted tool name (mail.send etc.)
// so cross-system joins stay readable.

import { randomUUID } from 'node:crypto';
import { recordIntent, recordExecution } from './ledger.js';

const ZEHRAVA_URL = (process.env.ZEHRAVA_URL || 'http://zehrava:4000').replace(/\/$/, '');
const AGENT_NAME = process.env.DIWAN_AGENT_NAME || `diwan-crm-support-${randomUUID().slice(0, 8)}`;
const AGENT_RISK_TIER = process.env.DIWAN_AGENT_RISK_TIER || 'standard';
const POLL_INTERVAL_MS = 1000;
const POLL_TIMEOUT_MS = 30_000;

// Map agent-harness tool names → Zehrava (policy, destination). Zehrava rejects
// unknown destinations with the policy's allowlist, so we have to use a real
// destination from each policy's `destinations` field.
const TOOL_POLICY_MAP = {
  'mail.send':  { policy: 'support-reply',    destination: 'intercom.reply' },
  'db.write':   { policy: 'crm-low-risk',     destination: 'hubspot.contacts' },
  'web.fetch':  { policy: 'internal-publish', destination: 'notion.workspace' },
  'api.post':   { policy: 'internal-publish', destination: 'confluence.internal' },
};

// Module-scope agent identity. Per-run process so cache is not persisted to
// disk — each agent-harness invocation registers a fresh agent row, which is
// fine for the demo (Zehrava's `agents` table grows but `name` is not unique).
let _agentApiKey = null;
let _agentId = null;
let _agentRegisterPromise = null;

async function http(method, path, { body, apiKey } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`;
  const res = await fetch(`${ZEHRAVA_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try { json = text ? JSON.parse(text) : {}; } catch { json = { raw: text }; }
  if (!res.ok) {
    const e = new Error(json.error || `HTTP ${res.status}`);
    e.status = res.status;
    e.body = json;
    throw e;
  }
  return json;
}

async function registerAgent() {
  if (_agentApiKey) return { agentId: _agentId, apiKey: _agentApiKey };
  if (_agentRegisterPromise) return _agentRegisterPromise;
  _agentRegisterPromise = (async () => {
    const created = await http('POST', '/v1/agents/register', {
      body: { name: AGENT_NAME, riskTier: AGENT_RISK_TIER },
    });
    _agentApiKey = created.apiKey;
    _agentId = created.agentId || created.agent_id;
    if (!_agentApiKey) throw new Error('Zehrava /v1/agents/register did not return apiKey');
    if (process.env.DIWAN_DEBUG) console.error(`[intent] registered ${AGENT_NAME} → ${_agentId}`);
    return { agentId: _agentId, apiKey: _agentApiKey };
  })();
  try { return await _agentRegisterPromise; }
  finally { _agentRegisterPromise = null; }
}

export function getAgentId() { return _agentId; }

function buildIntent(toolName, args, traceId) {
  const map = TOOL_POLICY_MAP[toolName] || { policy: 'support-reply', destination: 'intercom.reply' };
  return {
    payload: JSON.stringify(args || {}).slice(0, 4000),
    destination: map.destination,
    policy: map.policy,
    recordCount: Array.isArray(args?.records) ? args.records.length : 1,
    metadata: {
      tool: toolName,
      args,
      trace_id: traceId,
    },
    idempotency_key: `${traceId}:${toolName}:${randomUUID()}`,
    expiresIn: '5m',
    _toolName: toolName,
    _policyName: map.policy,
  };
}

export async function submitIntent(toolName, args, traceId) {
  const { agentId, apiKey } = await registerAgent();
  const body = buildIntent(toolName, args, traceId);
  const { _toolName, _policyName, ...wireBody } = body;

  const created = await http('POST', '/v1/intents', { body: wireBody, apiKey });
  const intentId = created.intentId || created.proposalId || created.id;
  let status = created.status;
  let last = created;

  if (status === 'pending_approval') {
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    while (Date.now() < deadline && status === 'pending_approval') {
      await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
      try {
        last = await http('GET', `/v1/intents/${intentId}`, { apiKey });
        status = last.status;
      } catch (e) {
        // transient error — keep polling
      }
    }
  }

  // Mirror intent into /data/diwan.db. Use the dotted tool name as the
  // destination so the demo ledger stays human-readable; Zehrava's view of
  // `intercom.reply` etc. lives in /data/gate.db separately.
  const runId = process.env.DIWAN_RUN_ID || null;
  recordIntent({
    intentId,
    traceId,
    runId,
    agentId,
    destination: toolName,
    payload: wireBody.payload,
    status,
    policyName: _policyName,
    idempotencyKey: wireBody.idempotency_key,
  });

  // For approved intents, mint an execution row immediately. Status starts
  // at 'issued'; tools.js flips it to succeeded/failed after the side effect.
  let executionToken = null;
  if (status === 'approved') {
    executionToken = `exec_${randomUUID().replace(/-/g, '').slice(0, 16)}`;
    recordExecution({
      executionToken,
      intentId,
      traceId,
      runId,
      status: 'issued',
    });
  }

  return {
    intentId,
    executionToken,
    status,
    blockReason: last.blockReason || last.block_reason || null,
    raw: last,
  };
}

// Best-effort outcome report. Zehrava 0.3.0 doesn't ship /v1/intents/:id/outcome
// — we keep the call so a future Zehrava that adds it Just Works, but failures
// are silent. Authoritative outcome lives in /data/diwan.db side_effect rows.
export async function reportOutcome(intentId, outcome) {
  try {
    const { apiKey } = await registerAgent();
    await http('POST', `/v1/intents/${intentId}/outcome`, { body: outcome, apiKey });
  } catch (e) {
    if (process.env.DIWAN_DEBUG) console.error('[intent] outcome report failed:', e.message);
  }
}
