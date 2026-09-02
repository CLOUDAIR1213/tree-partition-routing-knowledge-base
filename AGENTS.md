# Project Agent Rules

## Documentation-First Workflow

- Before changing code, read `docs/README.md`, `docs/architecture/system-overview.md`, the relevant end-to-end feature document, and every shared document that feature document references.
- Use the task-to-document matrix in `docs/README.md`; do not infer current behavior from filenames or archived specifications.
- After reading the documents, inspect the actual code, tests, OpenAPI contract, and Git worktree. If they disagree, surface the mismatch and use the user-selected code baseline rather than silently trusting stale prose.
- Check the file boundary table before editing. `owned` files are normally in scope; `shared` files require consumer and contract impact checks; `generated` files must be regenerated; `runtime-data` must not be changed for ordinary validation; `approval-required` changes need explicit direction.
- When a task changes behavior, state transitions, API semantics, storage, configuration, security invariants, or file ownership, update the relevant feature document in the same task.
- New capabilities remain in “Known limitations and follow-up plans” until code and focused validation exist. Do not document planned or unconnected code as implemented.
- Files under `docs/archive/` are historical context only and are not a source of current behavior.

## Canonical Documentation

- `docs/features/` owns end-to-end feature behavior.
- `docs/architecture/` owns shared system and storage structure.
- `docs/contracts/api-conventions.md` owns API generation and error conventions; complete field definitions remain in OpenAPI.
- `docs/operations/local-development.md` owns startup and configuration guidance.
- `docs/testing/strategy.md` owns validation scope, isolation, and current test gaps.

## Validation Scope

- The coding agent is responsible for code health: compilation, linting, type checks, focused unit tests, and narrowly scoped contract checks.
- Do not run broad business acceptance, full end-to-end suites, routing evaluations, model-quality benchmarks, bulk seed scripts, or large model downloads unless the user explicitly requests them.
- Do not write validation data into persistent business stores under `data/raw`, `data/staging`, `data/indexes`, or `data/metadata` by default.
- Small, isolated test fixtures are allowed when necessary. Keep them in temporary directories or in-memory fakes and remove them through the test fixture lifecycle.
- Prefer read-only health checks for an already initialized local service. Do not mutate existing demo or user data merely to prove an endpoint works.
