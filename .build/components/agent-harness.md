# agent-harness component

**What**: Toy CRM-support agent for the demo. Calls an LLM (via Lobster Trap proxy), uses 4 tools (each gated by Zehrava), produces trajectories that exercise the full stack.

## Inputs

- LLM endpoint (env `OPENAI_BASE_URL=http://lobstertrap:8080/v1`)
- Zehrava endpoint (env `ZEHRAVA_URL=http://zehrava:4000`)
- LLM API key (env `OPENAI_API_KEY` or `GEMINI_API_KEY`)
- Optional: `DIWAN_DISABLE_GUARDS=1` for vulnerable-baseline mode in the gauntlet

## Tools

Four tools the agent can call:

| Tool | What it does | Zehrava intent type | Side-effect destination |
|---|---|---|---|
| `web.fetch(url)` | Fetches a URL, returns body. Used for indirect-injection scenarios. | `web.fetch` | logged only, no real network call to attacker domains |
| `db.write({table,op,where,values})` | Writes to a fake CRM SQLite. | `db.write` | local sqlite at `/data/crm.db` |
| `mail.send({to,subject,body})` | Pretends to send email. | `mail.send` | logged only (NEVER real send) |
| `api.post({url,headers,body})` | Generic webhook POST. | `api.post` | logged only |

Each tool wrapper:
1. POSTs an intent to Zehrava with the tool args
2. Waits for verdict (`approved` / `pending_approval` / `blocked` / `duplicate_blocked`)
3. If approved, simulates the side effect and POSTs the outcome back to Zehrava
4. Returns the result to the LLM

## Tasks owned

- **T1.5** — initial scaffold (package.json, OpenAI SDK, 4 tool stubs)
- **T2.3** — full end-to-end trajectory test
- **T3.4** — `DIWAN_DISABLE_GUARDS=1` mode for gauntlet baseline

## Acceptance criteria

- `docker compose run --rm agent-harness "Send a welcome email to john@example.com"` produces:
  - 1 prompt row + 1 response row + verdict rows in the ledger
  - 1 intent row (`mail.send`) + 1 execution row + 1 side_effect row in the ledger
  - All sharing one `trace_id`
- `DIWAN_DISABLE_GUARDS=1 docker compose run --rm agent-harness "..."` skips Zehrava entirely; only Lobster Trap rows appear (no `intent`/`execution`/`side_effect`)
- `agent-harness` accepts a single CLI arg (the user prompt) and exits after the agent completes its turn

## Reference docs

- OpenAI Node SDK: https://github.com/openai/openai-node
- Zehrava intent API: `zehrava/SPEC.md`
- Zehrava JS SDK: `zehrava/packages/gate-sdk-js/`

## Fallback if blocked

- **Tool-calling format mismatch**: standard OpenAI tool-calling format works with Gemini's OpenAI-compat endpoint. If not, drop to ReAct prose parsing (uglier but reliable).
- **Zehrava SDK doesn't expose what we need**: vendored code is mutable. Add helper methods directly.

## What NOT to do

- **NEVER actually send email or call external APIs.** All tools are mocked at the side-effect layer. The point is to demo governance, not real I/O.
- **NEVER use real customer data.** Seed with `john@example.com` style placeholders.
- Don't make the agent too smart. A 200-line scaffold is enough; we're not building Cursor.
