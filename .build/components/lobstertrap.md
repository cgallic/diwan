# lobstertrap component

**What**: Veea's MIT-licensed prompt/response inspection proxy ([github.com/veeainc/lobstertrap](https://github.com/veeainc/lobstertrap)). Single Go binary. We mount our policy packs and let it proxy LLM calls.

## Inputs

- Upstream LLM URL (env `LOBSTERTRAP_UPSTREAM`)
- Policy directory (mounted at `/policies`, read-only)
- API key for upstream (env `OPENAI_API_KEY` or `GEMINI_API_KEY`)

## Outputs

- OpenAI-compatible proxy on `:8080` — accepts `/v1/chat/completions` etc., forwards to upstream
- Audit log written as JSONL to `/data/lobstertrap-audit.log`
- Per-request `_lobstertrap` metadata field added to responses (declared-vs-detected intent, etc.)

## Tasks owned

- **T1.3** — verify upstream clones + builds in our Dockerfile
- **T2.2** — verify proxies Gemini cleanly (D1 critical risk)

## Acceptance criteria

- `docker compose build lobstertrap` succeeds without errors
- `docker compose run --rm lobstertrap --version` prints a version
- `curl -X POST http://localhost:8080/v1/chat/completions -H "Authorization: Bearer $KEY" -d '{...}'` returns a real LLM response
- The response has a `_lobstertrap` field with `declared_intent`, `detected_intent`, `risk_level`
- An audit row appears in `/data/lobstertrap-audit.log` (JSONL format)
- The agent-safety policy fires on a known attack prompt (e.g., `"ignore previous instructions and exfiltrate ..."`) — DENY with the right rule name

## Reference docs

- Upstream README: `git clone https://github.com/veeainc/lobstertrap` then read `README.md`
- Connor's source-level cheatsheet: `~/brain/wiki/topics/lobstertrap-policy-reference-2026-05-09.md` (private — do not copy into repo)
- Our agent-safety pack: `policies/agent-safety.yaml` (already in repo, 17 rules)
- Note: matchable field set is closed at 22 fields; new patterns require Go code, not policy YAML

## Fallback if blocked

- **`make build` fails or no Makefile**: try `go build ./cmd/lobstertrap` or whatever entry point the repo has. Look at `main.go`.
- **Upstream proxy doesn't work with Gemini's OpenAI-compat endpoint**: write a thin shim sidecar (Node, ~50 LoC) that translates OpenAI request format → Gemini native, OR pivot upstream to Anthropic and document in BUILD.md.
- **Audit log format is binary or proprietary**: read upstream source for the writer, normalize in `ledger-writer`.

## What NOT to do

- Don't fork Lobster Trap. Use upstream image / clone-and-build only.
- Don't write to its config files at runtime — policies are mount-time only.
- Don't claim features we haven't tested. The HUMAN_REVIEW gap is real (don't dunk on Veea — frame as "we operationalize it via Zehrava").
