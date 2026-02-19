# AGENTS.md Template

Use this file as a starting point for new repositories. Replace placeholders like `<PROJECT_NAME>` and remove sections that do not apply.

---

## Repository Context Docs (Mandatory)

Before starting any non-trivial task, read:

- `docs/repo_context_llm.md` (required first-pass context)

Use companion docs as needed:

- `docs/repo_technical_reference.md`
- `docs/repo_intuition_essay.md`

When behavior, data flow, CLI behavior, storage outputs, or run commands change, update these docs in the same change set.

---

## North Star

- Build `<PROJECT_NAME>` for reliability, auditability, and reproducibility.
- Prefer correctness and testability over speed.

---

## Scope Lock (Current Phase)

This repo is currently scoped to:

> `<DEFINE_EXACT_SCOPE>`

### In Scope (Allowed)
- `<RULE_1>`
- `<RULE_2>`

### Out of Scope (Not Allowed Without Approval)
- `<OUT_OF_SCOPE_1>`
- `<OUT_OF_SCOPE_2>`

### Expansion Rule
If expansion seems useful:
1. Stop implementation.
2. Propose expansion in `tasks/todo.md`.
3. Wait for explicit approval before continuing.

---

## How to Work in This Repo

### Plan Mode Default
Use plan mode for non-trivial tasks (3+ steps or architecture changes).

Plan must include:
- Data flow (inputs -> transforms -> outputs)
- Error handling and retries
- Storage/schema changes (if any)
- Test strategy (unit tests, mocked external dependencies)
- Rollback/safety checks

If implementation diverges from plan, stop and re-plan.

### Task Management Workflow
Follow this sequence:
1. Plan first in `tasks/todo.md` (checklist + acceptance criteria + minimal test plan).
2. Verify plan against scope and architecture before coding.
3. Track progress by checking off items as you complete them.
4. Add progress notes after major steps.
5. Add a Review section:
   - What changed
   - Why
   - How tested
   - How to run
   - Which docs were updated
6. Capture lessons in `tasks/lessons.md` for mistakes, corrections, or newly learned failure modes.

### Self-Improvement Loop
- Review `tasks/lessons.md` at session start and before large PRs.
- After issues/corrections, add:
  - What happened
  - Root cause
  - Preventative rule
  - Early detection signal

### Verification Before Done
Never mark done without proof:
- Tests ran and passed
- Outputs validated on known examples
- Logs reviewed
- Behavior checked against scope/spec

### Autonomous Bug Fixing
- Use logs/errors/failing tests first.
- Apply minimal targeted fixes.
- Avoid hand-holding unless required information is truly missing.

---

## Repo Conventions

### Branching and PR Hygiene
- Never work directly on `main`.
- Use `feat/<name>`, `fix/<name>`, or `chore/<name>`.
- Keep PRs narrow (one deliverable per PR).

### Commit Style
- Small commits with clear intent.
- Prefixes: `feat:`, `fix:`, `chore:`, `docs:`, `test:`.

### Code Quality
- Prefer small modules.
- Avoid magic constants; centralize configuration.
- Add type hints where useful.
- Log key events and failures.

---

## Testing Requirements

- No live-network dependency in unit tests.
- Mock external APIs/services.
- Add tests for happy paths plus edge cases/failures.
- Add migration/idempotency tests for schema/storage changes.

---

## Security and Compliance

- No secrets in repo.
- Read credentials from environment/secret manager.
- Store timestamps in UTC.
- Keep enough raw fields for audit/debug where needed.

---

## Agent Output Checklist (Before Finishing)

- [ ] `tasks/todo.md` has final plan and completion notes
- [ ] Tests added/updated and passing locally
- [ ] Schema/storage changes documented (if any)
- [ ] Example run command documented
- [ ] Context docs updated when behavior changed
- [ ] `tasks/lessons.md` updated for new learnings
- [ ] PR is narrow, reviewable, reproducible
