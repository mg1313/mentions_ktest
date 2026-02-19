# Documentation Rules for LLM-Driven Repos

This file summarizes the documentation/process rules already implemented in this repo, generalized for reuse in new repos.

## 1. Required Files

Create and maintain these files from day one:

- `AGENTS.md`: repo operating contract for LLM agents
- `tasks/todo.md`: live task plan, progress tracking, and completion review
- `tasks/lessons.md`: failure/correction log and preventative rules
- `docs/repo_context_llm.md`: first-pass technical context for fast onboarding
- `docs/repo_technical_reference.md`: detailed architecture and interfaces
- `docs/repo_intuition_essay.md`: high-level strategy and mental model

## 2. Task Lifecycle Rule

For every non-trivial task:

1. Plan first in `tasks/todo.md`.
2. Include acceptance criteria and minimal test plan.
3. Execute and check off items as work completes.
4. Add progress notes after major implementation steps.
5. Add a final Review section with:
   - what changed
   - why
   - how tested
   - how to run
   - which docs were updated
6. Add lessons in `tasks/lessons.md` when mistakes or corrections happen.

## 3. Planning Content Standard

A valid plan should explicitly cover:

- Inputs -> transforms -> outputs (data flow)
- Error handling and retry behavior
- Storage/schema changes (if any)
- Test strategy (mocked external systems, no network in unit tests)
- Rollback/safety checks

## 4. Documentation Sync Rule

When behavior changes, update docs in the same change set:

- Code behavior or data flow change -> update `docs/repo_context_llm.md`
- Interface/architecture change -> update `docs/repo_technical_reference.md`
- Strategy/mental model shift -> update `docs/repo_intuition_essay.md`
- Process/rules change -> update `AGENTS.md`

## 5. Lessons System Rule

Every `tasks/lessons.md` entry should include:

- Date
- What happened
- Root cause
- Preventative rule
- How to detect earlier

Use lessons to prevent repeated failures, not just to record history.

## 6. Verification Rule

Do not mark work done without evidence:

- Relevant tests executed and passing
- Outputs validated against expected examples
- Logs reviewed when runtime behavior matters
- Scope/spec compliance confirmed

## 7. Scope-Control Rule

- Define an explicit current scope in `AGENTS.md`.
- If proposed work expands scope, stop and request explicit approval.
- Record proposed expansion in `tasks/todo.md` before implementing.

## 8. Reproducibility Rule

Every task review should include runnable commands so another engineer (or agent) can reproduce results without extra context.

## 9. Suggested Starter Structure for New Repos

Use this minimal scaffold:

```text
AGENTS.md
docs/repo_context_llm.md
docs/repo_technical_reference.md
docs/repo_intuition_essay.md
tasks/todo.md
tasks/lessons.md
```

Pair this file with `agents_template.md` when bootstrapping a new repository.
