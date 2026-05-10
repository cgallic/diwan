# Diwan Build Orchestrator — Protocol

This file tells any Claude session how to advance the Diwan build. The pattern is **stateless**: every run reads `BUILD.md` for state, picks the next eligible task, ships it, updates `BUILD.md`, commits, reports.

## Trigger phrases

When the user says any of these in this repo, follow this protocol:
- "advance build"
- "next task"
- "diwan build run"
- "ship next"

## Protocol (every run)

### Step 1 — Read state

Read `BUILD.md` top-to-bottom. Identify:
- Today's date (use real-time, not memory)
- Current day in the build calendar (D-1, D1, D2, …)
- All `[ ]` todo and `[~]` in-progress tasks
- Any `[!]` blocked tasks

### Step 2 — Pick the next task

Selection priority:
1. Any `[~]` in-progress task that's stalled — ask user before resuming.
2. Any `[ ]` todo task whose dependencies are all `[x]` done. Within today's day-block first; only spill into next day if today is empty.
3. If no eligible tasks, report and stop.

### Step 3 — Read the component spec

Open the corresponding `.build/components/<name>.md`. The spec defines:
- What this component does
- Inputs / outputs
- Acceptance criteria ("done when...")
- Fallback if blocked

### Step 4 — Dispatch a subagent

Use the `Agent` tool with `general-purpose` (or a specialized type if appropriate). The subagent gets:
- The task ID + title from `BUILD.md`
- The full component spec
- The current ledger schema (if relevant)
- A pointer to upstream code (e.g., `veeainc/lobstertrap` for Lobster Trap tasks)
- The acceptance criteria
- A 200-word reporting bound

**Critical**: subagents MUST verify their output against acceptance criteria before reporting "done." Subagents that report success without verification are reverted on the next run.

### Step 5 — Verify

In the orchestrator session (not the subagent):
1. Run the relevant test (e.g., `docker compose build`, fire one trajectory, run a query)
2. If green, mark `[x]` in `BUILD.md`
3. If red, mark `[!]` with a one-line blocker note, do NOT mark done

### Step 6 — Commit

Single commit per task. Format:
```
<component>: <one-line summary> (T<X.Y>)

<2-3 line body explaining what changed>
```

Examples:
```
ledger-writer: SQLite schema + tail/normalize loop (T1.2)

Implements 9-table schema with trace_id index. Tails Lobster Trap audit log (JSONL),
parses each line, normalizes to schema, inserts with WAL.
```

### Step 7 — Report + chain

Post a 3-line summary:
```
✓ T<X.Y> shipped → commit <sha7> → next: T<X.Y>
```

Then **immediately continue to the next eligible task** (chain mode is default; this is a hackathon, not a code review).

**Auto-push after every successful task** — `git push origin main`. Connor wants visible progress on the public repo.

### Hard stops (when to actually stop and ping Connor)

Stop and post to Connor (with diagnostic detail) only when:
- A decision gate fires (D1 Lobster×Gemini, D3 attack count, D4 suggester effectiveness, D5 visual clarity, D6 record-once)
- A subagent returns a `[!]` blocked status
- A task fails its acceptance test 3 times in a row
- All eligible `[ ]` tasks are blocked
- Connor explicitly says "stop"

In all other cases: keep chaining.

### Parallelism

When multiple `[ ]` tasks have no shared dependencies, dispatch them as parallel subagents in a single Agent batch (multiple `Agent` tool calls in one message). Examples:
- D-1: T1.1, T1.3, T1.4, T1.5 are all independent — fire 4 subagents in parallel
- D2: each attack JSON file is independent — pattern-replicate in one go

## Hard rules

- **Never push to GitHub from an orchestrator run.** Only commit locally. User runs `git push` after review.
- **Never edit `BUILD.md` to remove or rewrite a task without user instruction.** Mark status only.
- **Never skip a decision gate.** If today is D3 evening and the gate hasn't been checked, run the gate test before shipping more.
- **Never mark `[x]` without verification.** "Done" requires the acceptance test to pass.
- **Run tests in the actual docker environment**, not stubbed locally. The whole point is reproducibility.
- **Docker access on the agent box**: connor was added to the `docker` group on 2026-05-09 but the current shell may not have docker membership cached yet. Use `sg docker -c "docker compose ..."` until next re-login. After re-login (`logout` + ssh back, or `newgrp docker`), `docker` works directly.

## When to escalate to user

- Decision gates fire (D1 Lobster×Gemini compat, D3 attack count, D4 suggester effectiveness, D5 visual clarity, D6 record-once).
- A task spec is ambiguous → ask before guessing.
- A test fails 3 times in a row → stop, post diagnostics.
- Connor mentions a paying KaiCalls/BWK customer in any task context → defer to him per [`feedback_no_customer_outreach`](https://github.com/cgallic/diwan does not contain this; it's in the private brain).

## When to use the Skill tool

Some tasks map to existing skills:
- D6 video recording → `kai-video-production` (Connor's existing skill)
- README polish → `kai-write` for marketing copy passes
- UI scaffold → `frontend-design` for the Next.js layout
- Demo screen recording / edit → `video-edit`

Prefer skills over rolling new logic when a fit exists.

## Cadence options

This orchestrator runs **on demand** (Connor types "advance build"). Two automation paths:

1. **Manual** (default): Connor opens this repo each morning, types "advance build" 1-3x.
2. **Scheduled**: use the `/schedule` skill to fire a remote agent daily at 09:00 EDT that reads BUILD.md, executes one task per run, posts to #AI SDR. Connor reviews the diff before next fire.

Connor picks. Default is manual until he says otherwise.

## Failure modes the orchestrator must handle

- **Lobster Trap doesn't proxy Gemini** (D1 risk): switch to Anthropic upstream, document in BUILD.md, continue.
- **A subagent edits the wrong file**: `git restore` and rerun with sharper prompt.
- **Two tasks have a hidden dependency**: insert a new task in BUILD.md with the dependency wired, mark the blocked one `[!]`.
- **A test passes locally but not in CI**: there is no CI. Tests run in `docker compose`. If it doesn't work there, it isn't done.
