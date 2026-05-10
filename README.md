# Diwan

**Preflight Tests and Decision Receipts for AI Agents.**

> **Diwan Preflight** attacks your agent before production and proves which policies reduce failures.
> **Diwan Receipts** records every production prompt, policy verdict, intent, execution token, and side effect in one replayable trace.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## What it is

AI agents read stuff — web pages, documents, prompts — and do stuff — send emails, update databases, transfer money. When they get either wrong, the company pays. Two different problems need two different answers: before launch, you need to know if the agent is safe enough to ship. After launch, you need evidence when something goes wrong.

Diwan answers both with one stack. **Lobster Trap** ([Veea](https://github.com/veeainc/lobstertrap), MIT) inspects the read-path. **Zehrava Gate** (open-sourced from a working POC, vendored here under [`zehrava/`](./zehrava)) gates the write-path. Both feed one ledger.

**Preflight** runs 20 enterprise attacks against your agent, scores how many fail, suggests Lobster Trap policies for the gaps, and reruns to show fewer failing scenarios. **Receipts** records every prompt and every action in one timeline — a *decision receipt* — joined by `trace_id`. Replay any agent's full trajectory.

Before launch you ship safer. After launch you have evidence.

---

## Quickstart

```bash
git clone https://github.com/cgallic/diwan
cd diwan
docker compose up
```

Boots in <30 seconds. Open `http://localhost:3000`.

### Preflight (pre-prod gauntlet)

```bash
# Run the 20-attack suite against the bundled CRM agent
docker compose exec gauntlet diwan preflight run --agent crm-support

# Generate Lobster Trap policy drafts for the gaps
docker compose exec gauntlet diwan preflight suggest-policies

# Rerun and see the before/after
docker compose exec gauntlet diwan preflight rerun
```

### Receipts (runtime)

Point your agent's OpenAI base URL at `http://localhost:8080` (Lobster Trap proxy). Every prompt, response, intent, and execution lands in the SQLite ledger and surfaces in the UI.

---

## Architecture

```
┌──────────────┐                    ┌──────────────┐
│   Agent      │                    │ Agent tool   │
│   (your code)│                    │ calls        │
└──────┬───────┘                    └──────┬───────┘
       │ LLM calls                         │ writes
       ▼                                   ▼
┌──────────────┐                    ┌──────────────┐
│ Lobster Trap │                    │ Zehrava Gate │
│ (read-path)  │                    │ (write-path) │
└──────┬───────┘                    └──────┬───────┘
       │ audit log                         │
       ▼                                   │
┌──────────────┐                           │
│ ledger-writer│                           │
│ (normalizer) │                           │
└──────┬───────┘                           │
       │                                   │
       └───────────┬───────────────────────┘
                   ▼
          ┌────────────────┐
          │  SQLite ledger │  ← one trace_id per trajectory
          │  diwan.db   │
          └────────┬───────┘
                   │
                   ▼
          ┌────────────────┐
          │  ui   │
          │  - Preflight   │  before/after scoreboard
          │  - Receipts    │  per-trace timeline
          │  - Review queue│  HUMAN_REVIEW handler
          └────────────────┘
```

5 services + SQLite ledger. Reproducible via `docker compose up`.

---

## Repository layout

| Path | What |
|---|---|
| [`policies/`](./policies) | Lobster Trap YAML policies. `agent-safety.yaml` is the default-on production pack (17 rules, validated against Lobster Trap's 22-field matchable set). `hipaa.example.yaml` and `soc2-finance.example.yaml` are starter scaffolds users can extend. |
| [`zehrava/`](./zehrava) | Vendored Zehrava Gate — write-path policy + intent lifecycle + signed execution tokens. Originally [cgallic/zehrava-gate](https://github.com/cgallic/zehrava-gate); open-sourced into this monorepo. |
| [`lobstertrap/`](./lobstertrap) | Lobster Trap proxy ([upstream](https://github.com/veeainc/lobstertrap)) + custom config. |
| [`agent-harness/`](./agent-harness) | Toy CRM support agent for the demo (4 tools: `web.fetch`, `db.write`, `mail.send`, `api.post`). |
| [`ledger-writer/`](./ledger-writer) | Tails Lobster Trap's audit log, normalizes events, inserts into SQLite. |
| [`ui/`](./ui) | Next.js + tRPC + SQLite. Preflight scoreboard, per-trace timeline, HUMAN_REVIEW queue. |
| [`gauntlet/`](./gauntlet) | Preflight CLI + 20-attack suite + 20 template policy scaffolds. |
| [`scripts/`](./scripts) | dev convenience scripts. |
| [`docs/`](./docs) | longer-form docs (PRD, attack catalogue, policy reference). |

---

## How it operationalizes Lobster Trap's HUMAN_REVIEW

Lobster Trap's `HUMAN_REVIEW` action is observability-only by default — the upstream pipeline records the verdict but does not block the request. Diwan ties HUMAN_REVIEW verdicts to Zehrava Gate's execution gate: when Lobster Trap returns `HUMAN_REVIEW` on a write-path-relevant response, Zehrava holds the execution token until a reviewer either approves or denies in the UI's review queue. The agent never proceeds on its own. Same primitive, made enforceable.

---

## Compliance hooks

Decision receipts are designed to satisfy:

- **EU AI Act Article 12** — per-event logging for high-risk AI systems
- **NIST AI RMF** — GOVERN-1.4, MEASURE-2.7
- **SOC2** — CC7.x (system operations + change management)
- **HIPAA** — §164.312(b) (audit controls)

The buyer is the platform/security team that has to (a) gate which agents go to production and (b) produce evidence when something goes wrong after they do. The day-to-day pull is internal investigation, not external audit.

---

## License

MIT. See [LICENSE](./LICENSE).

Built on [Lobster Trap](https://github.com/veeainc/lobstertrap) (Veea, MIT) and Zehrava Gate (Connor Gallic, now MIT here).

---

## Status

Hackathon submission for [TechEx Intelligent Enterprise Solutions Hackathon](https://lablab.ai/ai-hackathons/techex-intelligent-enterprise-solutions-hackathon) (May 11–19, 2026). Track 1 (Agent Security & AI Governance, sponsored by Veea), Track 2 reference (Google AI Studio).
