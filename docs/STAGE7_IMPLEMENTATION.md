# Stage 7: Metamorphosis baseline

Metamorphosis adds a persisted full-project migration session around the
verified Stage 6 transformations. It creates a dependency-aware task graph,
executes only authorized immutable snapshot files, stores checkpoints and
events, writes a generated target directory, and exports a ZIP artifact.

## Implemented

- Typed migration request with project, StackForge configuration, plan,
  selected paths, mode, language, strategy, validation, and approval settings.
- Persistent migration sessions, task state, events, generated-file provenance,
  source/target hashes, and output paths.
- DAG task compilation for snapshot verification, target preparation,
  per-file transformation, and final validation.
- Deterministic scheduling based on task dependencies.
- Cancellation before execution and durable status/event reporting.
- Authorized migration status, event, and ZIP export endpoints.
- Target output assembly with traversal-safe paths and a migration manifest.
- Frontend “Run Metamorphosis” control connected to the selected project,
  latest StackForge configuration, selected snapshot files, and execution
  status.

## API

- `POST /api/v1/projects/{id}/metamorphosis`
- `POST /api/v1/metamorphosis/{id}/execute`
- `GET /api/v1/metamorphosis/{id}`
- `POST /api/v1/metamorphosis/{id}/cancel`
- `GET /api/v1/metamorphosis/{id}/events`
- `GET /api/v1/metamorphosis/{id}/export`

## Boundaries

The current engine supports partial/selected migrations using the Stage 6
deterministic adapters. It does not claim universal full-stack migration,
framework reconstruction, dependency installation, generated-code execution,
parallel worker isolation, arbitrary resume after process failure, or
behavioral equivalence. Tasks that fail remain recorded and are never reported
as completed. Later extensions can add specialized coordinators without
changing the migration request, task, event, provenance, or artifact contracts.
