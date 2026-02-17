# AGENTS.md

This repo is built with agentic development in mind. Agents must follow the workflows and guardrails below to keep changes correct, reviewable, and reproducible.

---

## Repository Context Docs (Mandatory)

Before starting any non-trivial task, read:

- `docs/repo_context_llm.md` (required first-pass context for fast full-repo understanding)

Use these companion docs as needed:

- `docs/repo_technical_reference.md` (detailed technical map)
- `docs/repo_intuition_essay.md` (high-level intuition and strategy framing)

When code behavior, data flow, CLI behavior, storage outputs, or run commands change, update these docs in the same change set.

---

## North Star

- Build a reliable, testable pipeline to **discover Kalshi Mentions → Sports markets**, **poll order books**, and compute **execution-realistic VWAP** for budget-sized trades.
- Prefer correctness, auditability, and reproducibility over speed.

---
---

## Scope Lock: Mentions → Sports ONLY (Current Phase)

**This project is currently scoped exclusively to:**

> https://kalshi.com/category/mentions/sports

Agents MUST treat this as a hard constraint.

### In-Scope (Allowed)
- Markets whose:
  - category == "Mentions"
  - subcategory/tag == "Sports"
- Series and markets reachable from the Mentions → Sports category
- Discovery via Kalshi API filters that map directly to this category/tag
- Order books, pricing, and metadata for these markets only

### Out-of-Scope (Not Allowed Without Explicit Approval)
- Any non-Mentions markets
- Mentions → Politics, Economics, Climate, Crypto, etc.
- Any attempt to generalize discovery logic to “all categories”
- Modeling, storage, or logic designed for cross-category reuse
- Commentary or data ingestion for non-sports events

### Expansion Rule
If an agent believes expanding scope is beneficial:
1. STOP implementation
2. Propose scope expansion in `tasks/todo.md`
3. Wait for explicit user approval before proceeding

No silent scope expansion is permitted.


## How to Work in This Repo

### Plan Mode Default
Use plan mode for any non-trivial task (3+ steps or any architectural decision).

**Plan must include:**
- Data flow (inputs → transforms → outputs)
- Error handling and retries
- Storage schema changes (if any)
- Test strategy (pytest, no network)
- Rollback plan / safety checks

If something goes sideways: **STOP, re-plan**. Don’t keep pushing.

---

## Subagent Strategy

Use subagents liberally to keep context clean:
- Research/reading docs
- Exploring API payload shapes
- Designing schema and indexes
- Writing tests
- Doing a quick adversarial review ("how does this break?")

One task per subagent.

---

## Self-Improvement Loop

After any correction from the user or a discovered mistake:
- Update `tasks/lessons.md` with:
  - What happened
  - Root cause
  - Preventative rule
  - How to detect it earlier
- Review `tasks/lessons.md` at the start of each session and before large PRs.

---

## Verification Before Done

Never mark a task “done” without proof:
- Tests run
- Output validated against known examples
- Logs reviewed
- Behavior verified against spec

Ask yourself: **Would a staff engineer approve this?**

---

## Demand Elegance (Balanced)

For non-trivial changes:
- Pause and ask: “Is there a simpler, more elegant approach?”
- Avoid hacky fixes unless explicitly scoped as temporary—with a follow-up issue created.
- Don’t over-engineer obvious fixes.

---

## Autonomous Bug Fixing

If given a bug report:
- Fix it directly
- Use logs/errors/failing tests
- Avoid asking for hand-holding unless info is truly missing
- Keep fixes minimal and targeted

---

# Task Management Workflow

Agents MUST follow this sequence:

1) **Plan First**
- Write a checklist plan to `tasks/todo.md`
- Include acceptance criteria and a minimal test plan

2) **Verify Plan**
- Double-check plan against constraints and existing architecture BEFORE coding

3) **Track Progress**
- Mark checklist items complete in `tasks/todo.md` as you go

4) **Explain Changes**
- Add a high-level summary after each major implementation step in `tasks/todo.md`

5) **Document Results**
- Add a “Review” section in `tasks/todo.md` with:
  - What changed
  - Why
  - How tested
  - How to run
  - Which repo context docs were updated (if behavior changed)

6) **Capture Lessons**
- Update `tasks/lessons.md` with any new learnings

---

# Repo Conventions

## Branching / PR Hygiene
- Never work directly on `main`.
- Use feature branches: `feat/<short-name>`, `fix/<short-name>`, `chore/<short-name>`
- Keep PRs narrow:
  - One deliverable per PR
  - Avoid mixing refactors + features

## Commit Style
- Small commits that build a narrative
- Prefer: `feat:`, `fix:`, `chore:`, `docs:`, `test:`
- Commit messages should explain intent, not mechanics

## Code Style / Quality
- Prefer small modules over monolith scripts
- No “magic” constants: centralize in config
- Use type hints where helpful
- Add logging for key events (discovery, polling, errors, persistence)

---

# Project-Specific Guardrails (Kalshi)

## API / Data Rules
- **No browser automation**. Use API only.
- **No hard-coded secrets**. Read from environment variables.
- Store all timestamps in **UTC**.
- Capture the **raw payload** (or enough raw fields) to allow audit/debug later.
- Be explicit about **price conventions** (YES/NO bids/asks and level ordering).

## Rate Limits & Reliability
- Implement exponential backoff with jitter.
- Fail open on individual markets: one broken market cannot crash the entire poller.
- Use idempotent writes (primary keys) to avoid duplicates on retries.
- Add a “jittered schedule” so polling isn’t perfectly aligned to minute boundaries.

## Data Storage Principles
- SQLite is fine initially; design schema so Postgres migration is easy later.
- Normalize order book levels OR store JSON + derive tables—be consistent and documented.
- Index for the queries you will run:
  - by (`ticker`, `ts_utc`)
  - by (`ts_utc`)
  - by (`ticker`, `side`, `level_rank`) if levels are normalized

## VWAP / Execution Realism
- VWAP must be computed by **walking book depth**, not midpoint.
- Use **budget-based sizing** ($25/$50/$100 etc.)
- Handle partial fills at final level.
- If depth insufficient, store NULL + reason flag.

## Discovery / Universe Refresh
- Separate “discover open markets” from “poll order books”.
- Refresh market universe every **15 minutes** (configurable).
- Poll active set every **3 minutes** (configurable).
- Active set selection should be explicit and testable:
  - close_time within N hours OR
  - volume/open_interest threshold OR
  - manually pinned list

---

# Testing Requirements (pytest, no network)

Agents must:
- Mock all API responses
- Unit test VWAP:
  - exact fill
  - partial last level
  - insufficient liquidity
- Unit test schema creation/migrations
- Unit test idempotent writes / dedupe on retries
- Unit test active-set filtering logic

Optional but recommended:
- Property-based tests for VWAP monotonicity (bigger budget => >= VWAP for buys)

---

# Observability

## Logging
Log at INFO:
- discovery counts, active-set size
- polling cycle start/end, duration
- per-market errors (with ticker)

Log at DEBUG:
- payload parsing issues, dropped fields

## Metrics (lightweight)
Track:
- number of markets discovered
- number polled successfully / failed
- DB write latency
- API response latency

---

# Security / Compliance

- Do not store credentials in repo.
- Don’t redistribute copyrighted content (e.g., broadcast audio/transcripts).
- This repo should only store market metadata and pricing/order book data.

---

# Agent Output Checklist (before finishing)

- [ ] `tasks/todo.md` contains the final reviewed plan and completion notes
- [ ] Tests added/updated and passing locally
- [ ] Schema changes documented
- [ ] Example run command documented
- [ ] Context docs updated when behavior changed (`docs/repo_context_llm.md`, `docs/repo_technical_reference.md`, `docs/repo_intuition_essay.md`)
- [ ] `tasks/lessons.md` updated if any new learning occurred
- [ ] PR is narrow, reviewable, and reproducible
