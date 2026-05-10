# ui component

**What**: Next.js + tRPC + better-sqlite3 web UI. Reads the ledger directly. Three views only — Preflight scoreboard, per-trace timeline, HUMAN_REVIEW queue. The hackathon's killer screenshot lives here.

## Inputs

- Read-only mount of ledger (env `LEDGER_PATH=/data/diwan.db`)
- Zehrava endpoint (env `ZEHRAVA_URL=http://zehrava:4000`) for HUMAN_REVIEW approve/deny actions
- Gemini API key (env `GEMINI_API_KEY`) for the trajectory classifier
- Gemini model (env `GEMINI_MODEL=gemini-3.1-pro`)

## Outputs

- HTTP server on `:3000`
- Three views (routes):
  - `/` — Preflight scoreboard (default landing)
  - `/trace/[trace_id]` — per-trajectory timeline
  - `/review` — HUMAN_REVIEW queue
- A POST to `/api/classify/<trace_id>` that calls Gemini once per trajectory and writes `thought_summary` row to the ledger

## Tasks owned

- **T2.4** — UI stub (D1)
- **T6.1** — full scaffold
- **T6.2** — Preflight scoreboard view
- **T6.3** — per-trace timeline view
- **T6.4** — HUMAN_REVIEW queue view
- **T6.5** — two-column visual asset → `docs/cover.png`
- **T6.6** — Gemini classifier integration

## View 1: Preflight scoreboard (`/`)

- Header: "Diwan Preflight"
- Section A: **Latest baseline run** — big number `13 / 20 FAILED` in red, list of 5 most-failed attacks with `trace_id` link
- Section B: **After-policies run** — `2 / 20 FAILED` in green, side-by-side with baseline
- Section C: **Before/after delta** — `85% fewer failing scenarios` huge font, count of suggested policies generated
- This view is the screenshot for slide 4 + cover image. Make it screenshot-worthy.

## View 2: Per-trace timeline (`/trace/[trace_id]`)

Vertical timeline of every event for one `trace_id`, ordered by `ts`:

```
[time] PROMPT   "Please summarize ..."             [agent: crm-support]
[time] VERDICT  ALLOW (ingress, rule_name)         [Lobster Trap]
[time] RESPONSE "Sure, fetching the doc ..."        [_lobstertrap: declared=summary, detected=summary]
[time] VERDICT  DENY (egress, block_indirect_injection)  [Lobster Trap]   ⚠ RED
[time] INTENT   web.fetch{url=...}                  [Zehrava: pending_approval]
[time] EXECUTION token=gex_... status=expired       [Zehrava]
[time] SIDE_EFFECT none                             [no actual fetch]
[time] THOUGHT_SUMMARY "OWASP LLM01 — indirect injection. Risk: critical." [Gemini 3.1 Pro]
```

Color: green ALLOW, red DENY/blocked, amber HUMAN_REVIEW, gray informational. Click any row to see the full payload JSON.

## View 3: HUMAN_REVIEW queue (`/review`)

Lists every `verdict` row with `action='HUMAN_REVIEW'` that hasn't been resolved. Each row has:
- The full prompt + response in expandable cards
- The Lobster Trap rule that fired
- The intent Zehrava is holding (with execution_token)
- Two buttons: ✅ Approve → POST `${ZEHRAVA_URL}/v1/intents/<id>/approve` ❌ Deny → POST deny

This is the **operationalize HUMAN_REVIEW** feature. Without this view, Lobster Trap's HUMAN_REVIEW is observability-only. With it, it actually blocks.

## Acceptance criteria

- `docker compose up ui` → http://localhost:3000 loads
- Preflight scoreboard shows real numbers from a real `attack_run` (no placeholder "lorem ipsum")
- Click any failed-attack row → routes to `/trace/[trace_id]` with full timeline
- HUMAN_REVIEW queue shows pending verdicts; clicking ✅ POSTs to Zehrava and the verdict disappears from the queue
- Two-column visual rendered as a `<TwoColumnVisual />` component, exportable to PNG via Playwright/Puppeteer to `docs/cover.png` (16:9, no UI chrome)
- Gemini classifier: visiting `/trace/<id>` triggers (lazily, once) a Gemini call; the result appears as a `thought_summary` row in the timeline
- No vanity metrics, no fake data, no design-system overhead. shadcn/ui defaults are fine.

## Reference

- Next.js 15+ app router, tRPC for the `/api/classify` route
- `better-sqlite3` for read access to the ledger
- Tailwind + shadcn defaults for styling
- For the Gemini call: use `@google/genai` SDK or fetch directly. One call per trace_id, structured output, thought summaries enabled.

## Fallback if blocked

- **Next.js + better-sqlite3 don't play nice** (native bindings in container): swap to a small Express server with `better-sqlite3`, render via React via `<script>` from CDN. Not pretty but ships.
- **Gemini API doesn't expose `thinking_level` from JS SDK yet**: just call vanilla `generateContent` with structured output. Thought summaries are nice-to-have, not load-bearing.
- **The Preflight scoreboard view doesn't have data because gauntlet hasn't run**: bake one full `attack_run` into the seed migration so the UI never starts empty.

## What NOT to do

- Don't add auth, settings, theme switcher, or any vanity feature. Three views, period.
- Don't waste time on animations beyond simple transitions.
- Don't build a generic dashboard with charts — this is investigative tooling, not a SaaS dashboard.
