# Diwan — Build Backlog

Source of truth for the 9-day hackathon build (May 10–18, 2026; submit May 18; finals May 19).

**To advance the build**: open this repo in Claude Code, say "advance build" — the orchestrator pattern in [`.build/orchestrator.md`](./.build/orchestrator.md) tells any Claude session what to do.

> **Build environment note (2026-05-09)**: docker is NOT installed on the agent box where most subagents run. D-1/D1 verification happens natively (npm install + `node`, Python, Go where applicable). Final container build + `docker compose up` integration test must run on a host with docker — Connor's laptop or a docker-equipped VPS. Decision: defer container builds until D2 morning when Connor's at a docker-capable machine.

**Status legend**: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked · `[-]` cut

---

## D-1 — Sunday May 10 (foundations, no integration yet)

- [x] **T1.1** SQLite schema design → `ledger-writer/schema.sql` with tables: `prompt`, `response`, `verdict`, `intent`, `execution`, `side_effect`, `thought_summary`, `attack_run`, `suggested_policy`. Every row has `trace_id` + `ts` + `run_id` (nullable; non-null only for gauntlet rows). See [`.build/components/ledger-writer.md`](./.build/components/ledger-writer.md).
- [x] **T1.2** `ledger-writer` Python: tail Lobster Trap audit log (JSONL), normalize each event into the schema, insert with WAL. ~150 LoC. *144 LoC + 146 LoC pure normalize + 165 LoC tests; 8/8 pass; trace_id falls through trace_id→request_id→X-Trace-Id→uuid4.*
- [x] **T1.3** Verify Lobster Trap upstream clones + builds in our Dockerfile (`make build` target name). If `make build` doesn't exist, find correct Go build invocation. *Real flags found: `--policy <FILE>`, `--listen <ADDR>`, `--audit-log`. No `--port`/`--policy-dir`. Audit log is JSONL with schema `timestamp/request_id/direction/action/rule_name/deny_message/metadata/prompt/declared_headers/mismatches/agent_id`. No env-var support.*
- [x] **T1.4** Fix Zehrava Dockerfile: vendored package is `packages/gate-server` (not `packages/server`). Rewire npm install path + entry point. *Native boot verified; docker build deferred — see "Build environment" note below.*
- [x] **T1.5** `agent-harness` Node init: `package.json`, OpenAI SDK pointing at `OPENAI_BASE_URL`, four tool stubs (`web.fetch`, `db.write`, `mail.send`, `api.post`) that POST to Zehrava for each. *Done — 5 files, ~428 LoC, npm install green, smoke test wired.*

**D-1 done when**: `docker compose build` succeeds for all 5 services without errors.

---

## D1 — Monday May 11 (HACKATHON STARTS — first end-to-end trajectory)

- [x] **T2.1** `docker compose up` boots all 5 services in <30s; healthchecks pass. *Verified 2026-05-09 21:46 EDT — boots in ~5s. UI remapped to host:3030 (host:3000 = open-webui).*
- [x] **T2.2** **Biggest D1 risk — verify Lobster Trap proxies Gemini cleanly.** *Pivoted upstream to local Ollama (qwen3.6:27b) — Lobster Trap's proxy uses ONLY backend's host+scheme (drops path), so Gemini's `/v1beta/openai` and OpenRouter's `/api` paths break. Ollama's `/v1/chat/completions` at root works natively. Bonus story: self-hosted, free, reproducible. Required normalize.py fix (T1.2 was schema-guessing before T1.3 returned). Verified end-to-end: ingress+egress audit rows hit ledger.*
- [x] **T2.3** One benign trajectory end-to-end: agent prompt → Lobster ALLOW verdict (logged) → response → agent invokes `db.write` → Zehrava intent → policy approved → execution token issued → side_effect logged. **Verify all 5 rows in SQLite share one `trace_id`.** *Verified — 2 intent + 2 execution + 2 side_effect rows in ledger after agent runs. trace_id propagation through Lobster Trap headers is a D3 flag.*
- [x] **T2.4** UI stub: Next.js boots at `:3000`, reads ledger, lists trace_ids. Don't polish yet. *Done via Node/HTTP stub on :8780 — exposes /health with trace_count + latest_trace. Real Next.js UI lands D5.*

**D1 done when**: one trace_id has 5+ rows visible in the UI, all from one agent action.

---

## D2 — Tuesday May 12 (ledger lock + 20-attack catalogue)

- [x] **T3.1** Lock the ledger schema (no more changes after today). Add SQL views for: `trace_summary`, `attack_run_summary`. *11/11 tests pass; 2 D3 flags noted (duplicate_blocked not counted as denial; human_review_pending is trace-scoped not intent-scoped).*
- [x] **T3.2** Expand attack catalogue from 5 → 20 attacks. Seed: `gauntlet/attacks/` directory, one JSON per attack. Spec: [`.build/components/gauntlet.md`](./.build/components/gauntlet.md). Pattern-replicate from the 5 documented attacks (in private wiki, also see public catalogue stub). *20/20 with real public incident anchors; categories all hit; 3 stretches flagged for D3.*
- [x] **T3.3** Each attack: trigger prompt + expected unguarded behavior + which policy rule (if any) catches it. *Covered by T3.2 schema — every JSON has trigger_prompt + expected_unguarded_behavior + matching_template.*
- [x] **T3.4** Vulnerable-agent variant: `agent-harness` accepts an env var `DIWAN_DISABLE_GUARDS=1` that skips Zehrava and runs raw against the model — used to baseline the gauntlet. *Covered by T1.5 — flag implemented in agent-harness.*

**D2 done when**: 20 attack JSON files exist; running each manually produces a fail (unguarded) and a different result (guarded).

---

## D3 — Wednesday May 13 (gauntlet CLI + scoring)

- [x] **T4.1** `diwan preflight run --agent <name>` CLI. Reads `gauntlet/attacks/*.json`, fires each via the agent harness, tags each event in the ledger with `run_id=<uuid>`. *Python CLI + Node shim. run_id propagated through agent-harness for intent/execution/side_effect rows; LT verdicts join via trace_id→attack_id map.*
- [x] **T4.2** Scoring: `diwan preflight score <run_id>` → JSON with per-attack pass/fail + total. Risk = % failed. *JSON output + ANSI summary view.*
- [x] **T4.3** Pretty terminal output: `13 / 20 FAILED — UNSAFE TO SHIP` with red/green per attack. *Reframed as `X/Y VULNERABILITIES REPRODUCED` for unguarded runs (clearer polarity).*
- [!] **T4.4** **Decision gate D3 FIRED 2026-05-09**: 3-attack baseline reproduced only 1/3 bad behaviors. **`qwen3.6:27b` is too aligned to be a vulnerable baseline.** Options: (A) less-aligned local model, (B) sharper jailbreak prompts, (C) weaker agent system prompt, (D) hand-curate to attacks that reproduce + scope down. Connor decides. CLI is correct; the input data needs work.

**D3 done when**: a baseline run produces a definite "X / Y FAILED" headline number, written to the ledger.

---

## D4 — Thursday May 14 (template policy suggester + before/after)

- [x] **T5.1** `gauntlet/templates/*.yaml` — 20 Lobster Trap policy template scaffolds keyed to attack patterns (one per attack class). Each has placeholders for detected metadata (target_domains, target_commands, etc.). *6 base + 14 specialized; 6/20 with placeholders; 1,137 LoC; all parse + field-validate.*
- [ ] **T5.2** `diwan preflight suggest-policies <run_id>` — for each failed attack, instantiate the matching template with detected metadata from the ledger, write to `policies/suggested-<run_id>/`.
- [ ] **T5.3** `diwan preflight rerun <baseline_run_id>` — restarts Lobster Trap with `policies/agent-safety.yaml` + `policies/suggested-<run_id>/*`, fires the same attacks, new run_id.
- [ ] **T5.4** Before/after diff: `diwan preflight diff <run_id_a> <run_id_b>` → JSON + table.
- [ ] **T5.5** **Decision gate D4**: did suggester drop fails by ≥70%? If not, fall back to **hand-curated policies** committed at `policies/curated/` and frame as "policy template library" (Veea engineers won't care that it's not LLM-synthesized — they'll care that it works).

**D4 done when**: `13 / 20 → 2 / 20` (or equivalent) is reproducible end-to-end via three CLI commands.

---

## D5 — Friday May 15 (UI polish + visual lock)

- [ ] **T6.1** UI scaffold complete: Next.js app router + tRPC + `better-sqlite3` reading ledger.
- [ ] **T6.2** **View 1 — Preflight scoreboard**: pick run_id pair, show side-by-side (X/Y failed before, X/Y failed after, % delta, count of suggested policies). The killer slide screenshot comes from here.
- [ ] **T6.3** **View 2 — Per-trace timeline**: click a trace_id, see vertical timeline (prompt → Lobster verdict → response → Zehrava intent → policy decision → execution → side_effect). Color: green ALLOW, red DENY, amber HUMAN_REVIEW.
- [ ] **T6.4** **View 3 — HUMAN_REVIEW queue**: lists pending HUMAN_REVIEW verdicts; click-to-approve/deny POSTs to Zehrava which releases or kills the held execution token. **This is what operationalizes Lobster Trap's HUMAN_REVIEW.**
- [ ] **T6.5** Two-column visual asset: build it once as a Next.js component, render to PNG (16:9), commit to `docs/cover.png`. Reuse for cover image, slide 3, README hero, GIF first frame.
- [ ] **T6.6** Gemini 3.1 Pro classifier: one call per trajectory, structured output, label against NIST AI RMF / OWASP LLM Top 10. Write to `thought_summary` rows.

**D5 done when**: UI screenshots match the §4 demo flow; cover image PNG ready.

---

## D6 — Saturday May 16 (record + ship)

- [ ] **T7.1** Record 3-minute demo video. Script from PRD §4 (in `~/brain/wiki/topics/kindling-prd-2026-05-09.md`). Use OBS or QuickTime; on-camera cold open per PRD.
- [ ] **T7.2** 5-slide deck (PDF). Per PRD §7. Tailwind/Pitch template fine.
- [ ] **T7.3** Record 6-second hero GIF: `docker compose up` → UI loads → one trajectory red row appears → click → timeline expands. Embed at top of README.
- [ ] **T7.4** Final README polish: open with the canonical framing, GIF, `docker compose up`, two-column diagram, repo layout, compliance hooks, MIT.

**D6 done when**: video + slides + GIF + README are submission-ready.

---

## D7 — Sunday May 17 (buffer + rehearsal)

- [ ] **T8.1** Reserved for bug fixes, video rerecord (max 1), spec corrections.
- [ ] **T8.2** Submission form draft (lablab fields per PRD §7).
- [ ] **T8.3** Verify `gh repo view cgallic/diwan` is public + README renders + GIF auto-plays.

---

## D8 — Monday May 18 (BUILD DAY — submit)

- [ ] **T9.1** Lablab build day participation (Discord active).
- [ ] **T9.2** Final freeze. No code changes after 6pm EDT.
- [ ] **T9.3** Submit on lablab.ai with all 8 fields filled.

---

## D9 — Tuesday May 19 (FINALS — remote)

- [ ] **T10.1** Remote — judges review submissions on stage at AI & Big Data Expo, San Jose.

---

## Decision gates (re-stated for clarity)

| Gate | When | Test | If fail |
|---|---|---|---|
| Lobster × Gemini compat | D1 evening | one chat completion through proxy | shim, OR pivot upstream to Anthropic |
| Attack reproducibility | D3 evening | ≥15 of 20 fail-close cleanly | drop count, adjust headline |
| Suggester effectiveness | D4 evening | rerun drops fails by ≥70% | fall back to hand-curated policies |
| Tool-use spoofing visual | D5 evening | UI flag is unambiguous | drop runtime demo to commitment+DROP_TABLE |
| Video record-once | D6 evening | first take is good enough | max 1 rerecord, no more on D7 |

## Out-of-scope (don't build)

- Generic governance dashboard / vanity charts
- CSV export
- Shareable trajectory links
- Fancy auth or RBAC for the UI
- Polished design system (Tailwind defaults are fine)
- Markdown-image exfiltration attack (cut from runtime demo)
- HIPAA/SOC2 production policy packs (scaffolds only)
- Upstream Lobster Trap PR (only if D-3 has slack)

## Working with the orchestrator

See [`.build/orchestrator.md`](./.build/orchestrator.md) for the protocol any Claude session uses to advance this backlog.

## Working with the components

Per-component specs:
- [`.build/components/lobstertrap.md`](./.build/components/lobstertrap.md)
- [`.build/components/zehrava.md`](./.build/components/zehrava.md)
- [`.build/components/ledger-writer.md`](./.build/components/ledger-writer.md)
- [`.build/components/agent-harness.md`](./.build/components/agent-harness.md)
- [`.build/components/gauntlet.md`](./.build/components/gauntlet.md)
- [`.build/components/ui.md`](./.build/components/ui.md)
