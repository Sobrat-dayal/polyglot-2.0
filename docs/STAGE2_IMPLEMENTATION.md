# Stage 2 Foundation Implementation

## Delivered

The FastAPI foundation now creates a guest personal workspace, blank projects,
safe ZIP imports, and GitHub archive imports. Each import creates an immutable
snapshot directory and a measured file inventory containing relative path,
size, SHA-256, language hint, binary flag, and selection state. Files can be
searched, previewed read-only, and selected for later analysis.

Projects support metadata updates, archive/restore, deletion with snapshot
cleanup, and activity history. Workspace and project records are persisted in
the existing SQLite database and initialized idempotently alongside translation
history.

Accounts use PBKDF2 password hashes and signed HttpOnly session cookies.
Project/workspace listing, creation, file preview, job creation, artifact
uploads, and artifact downloads check workspace membership. Jobs persist queued,
running, completed, and cancelled states, support idempotency keys, and expose
bounded local execution. Artifacts are stored by generated ID with measured
size and SHA-256 metadata.

## Security decisions

- ZIP paths are normalized with `PurePosixPath`; absolute paths, `..`, empty
  names, symlinks, oversized entries, file-count limits, and extraction quotas
  are rejected before files become visible.
- GitHub downloads are restricted to HTTPS `github.com` and use only a
  server-side `GITHUB_TOKEN` when configured.
- Imported source is never parsed by a build tool, executed, or used to run
  package lifecycle scripts.
- Preview paths are resolved beneath the project snapshot root.

## Deferred infrastructure

The repository does not yet include SQLAlchemy/Alembic, Redis/Celery, SSE/
WebSockets, or S3. The local worker and filesystem storage are deliberate
development implementations; production deployment should replace those
adapters without changing the project/snapshot API.
