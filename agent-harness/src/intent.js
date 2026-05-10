// src/intent.js — minimal Zehrava /v1/intents client.
// POSTs an intent, polls for a verdict if pending, reports outcomes back.

import { randomUUID } from 'node:crypto';

const ZEHRAVA_URL = (process.env.ZEHRAVA_URL || 'http://zehrava:4000').replace(/\/$/, '');
const ZEHRAVA_API_KEY = process.env.ZEHRAVA_API_KEY || 'gate_sk_demo';
const POLL_INTERVAL_MS = 1000;
const POLL_TIMEOUT_MS = 30_000;

function authHeaders() {
  return {
    'Authorization': `Bearer ${ZEHRAVA_API_KEY}`,
    'Content-Type': 'application/json',
  };
}

async function http(method, path, body) {
  const res = await fetch(`${ZEHRAVA_URL}${path}`, {
    method,
    headers: authHeaders(),
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

// Map a tool call → an intent. The shape mirrors gate-sdk-js.propose() so the
// existing /v1/intents endpoint accepts it without modification.
function buildIntent(toolName, args, traceId) {
  return {
    payload: JSON.stringify(args).slice(0, 4000),
    destination: toolName,                  // e.g. "mail.send"
    policy: `tool.${toolName}`,             // policy id; Zehrava resolves or defaults
    recordCount: Array.isArray(args?.records) ? args.records.length : 1,
    metadata: {
      tool: toolName,
      args,
      trace_id: traceId,
    },
    idempotency_key: `${traceId}:${toolName}:${randomUUID()}`,
    expiresIn: '5m',
  };
}

export async function submitIntent(toolName, args, traceId) {
  const body = buildIntent(toolName, args, traceId);
  const created = await http('POST', '/v1/intents', body);
  // proposals.js returns { proposalId, status, ... }; v1 alias preserves that.
  const intentId = created.intentId || created.proposalId || created.id;
  let status = created.status;
  let last = created;

  if (status === 'pending_approval') {
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    while (Date.now() < deadline && status === 'pending_approval') {
      await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
      try {
        last = await http('GET', `/v1/intents/${intentId}`);
        status = last.status;
      } catch (e) {
        // transient error — keep polling
      }
    }
  }

  return {
    intentId,
    status,
    blockReason: last.blockReason || last.block_reason || null,
    raw: last,
  };
}

// Best-effort outcome report after a side-effect ran.
// We use /v1/executions/:id/report when we have an executionId, but for the
// toy harness we just POST a metadata-only "outcome" event the ledger picks up.
export async function reportOutcome(intentId, outcome) {
  try {
    await http('POST', `/v1/intents/${intentId}/outcome`, outcome);
  } catch (e) {
    // Endpoint may not exist on this build; swallow — the side-effect log file
    // is the authoritative record for the demo.
    if (process.env.DIWAN_DEBUG) console.error('[intent] outcome report failed:', e.message);
  }
}
