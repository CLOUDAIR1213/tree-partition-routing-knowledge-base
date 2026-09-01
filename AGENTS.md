# Project Agent Rules

## Validation Scope

- The coding agent is responsible for code health: compilation, linting, type checks, focused unit tests, and narrowly scoped contract checks.
- Do not run broad business acceptance, full end-to-end suites, routing evaluations, model-quality benchmarks, bulk seed scripts, or large model downloads unless the user explicitly requests them.
- Do not write validation data into persistent business stores under `data/raw`, `data/staging`, `data/indexes`, or `data/metadata` by default.
- Small, isolated test fixtures are allowed when necessary. Keep them in temporary directories or in-memory fakes and remove them through the test fixture lifecycle.
- Prefer read-only health checks for an already initialized local service. Do not mutate existing demo or user data merely to prove an endpoint works.
