# zehrava component

**What**: Connor's vendored write-path policy engine. Originally [cgallic/zehrava-gate](https://github.com/cgallic/zehrava-gate); now MIT under `zehrava/` in the diwan monorepo. Implements the intent → policy → execute → verify lifecycle with idempotency keys, fail-closed semantics, and signed execution tokens.

## Inputs

- Policy directory at `/policies` (mounted from `zehrava/policies/` in the repo)
- Ledger path (env `ZEHRAVA_LEDGER_PATH=/data/diwan.db`)
- Fail-closed flag (env `ZEHRAVA_FAIL_CLOSED=true`)

## Outputs

- HTTP API on `:4000` — agent submits intents via `POST /v1/intents`
- Ledger rows for: `intent` (every submission), `execution` (if approved), `side_effect` (after worker confirmation)
- HUMAN_REVIEW queue — when Lobster Trap response was tagged HUMAN_REVIEW, Zehrava holds the execution token until a reviewer decides

## Tasks owned

- **T1.4** — fix Dockerfile npm install path (`packages/server` → `packages/gate-server`)
- (later) wire the HUMAN_REVIEW queue handler

## Acceptance criteria

- `docker compose build zehrava` succeeds
- `docker compose up zehrava` boots without errors
- `curl http://localhost:4000/v1/agents/register -d '{"name":"test","riskTier":"standard"}'` returns an `agentId` + `apiKey`
- `curl -X POST http://localhost:4000/v1/intents` with a valid policy decision returns `status: "approved"` or `"pending_approval"` per policy
- `intent` rows appear in the SQLite ledger
- A second submission with the same `idempotencyKey` returns `status: "duplicate_blocked"`

## Reference docs

- Vendored README: `zehrava/README.md`
- Vendored SPEC: `zehrava/SPEC.md` — intent lifecycle definitions
- Original repo: still at `cgallic/zehrava-gate` (now also MIT under our tree)
- Existing example policies in `zehrava/policies/` (5 files, useful starting point)

## Fallback if blocked

- **The `gate-server` package's entry point is unclear**: read `zehrava/packages/gate-server/index.js` or `package.json` `"main"` field
- **Node/npm version conflicts**: the vendored code targets Node 18+. If `npm ci` fails, use `npm install --legacy-peer-deps`
- **Policies don't load**: the policy YAML format here is Zehrava's, not Lobster Trap's. Don't confuse them. Zehrava policies live in `zehrava/policies/`.

## What NOT to do

- Don't rewrite Zehrava — it's a working POC, just dockerize it
- Don't change the V2 SDK API surface — keep `propose`/`approve`/`execute`/`verify` as-is
- Don't expose Zehrava's HTTP API publicly — internal docker network only
