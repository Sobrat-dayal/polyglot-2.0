# Polyglot 2.0

Polyglot 2.0 is a developer-focused AI translation and project inspection
workspace. Stage 1 provides the Monaco translator and protected Gemini/NVIDIA
NIM/Groq adapters. Stage 2 adds persistent guest workspaces, project
management, immutable source snapshots, public/authorized GitHub imports,
safe ZIP imports, file inventory/search/selection, lifecycle actions, and
activity history.

## Run locally (PowerShell)

```powershell
Copy-Item .env.example .env
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi "uvicorn[standard]" httpx google-genai pydantic-settings python-dotenv pytest
uvicorn app:app --reload --port 8000
```

In another terminal:

```powershell
npm ci
$env:POLYGLOT_API_URL = "http://127.0.0.1:8000"
$env:NEXT_PUBLIC_POLYGLOT_API_URL = "http://127.0.0.1:8000"
npm run dev
```

Open `http://localhost:3000`. Add a provider key to `.env` before requesting a
live translation. Keys and the optional `GITHUB_TOKEN` are read only by the
API process.

## Stage 2 API

- `GET /api/v1/workspaces` and `POST /api/v1/workspaces`
- `GET /api/v1/projects?workspace_id=&search=`
- `POST /api/v1/projects` for blank projects
- `POST /api/v1/projects/import/zip` with an `application/zip` body
- `POST /api/v1/projects/import/github` with `repository`, optional `branch`,
  and optional `workspace_id`
- `GET /api/v1/projects/{id}/files` with bounded path search
- `GET /api/v1/projects/{id}/files/{path}` for read-only source preview
- `POST /api/v1/projects/{id}/files/select` to persist selections
- `PATCH`, archive/restore, `DELETE`, and activity endpoints for projects
- `GET /api/v1/jobs` for the durable job-monitoring contract (job execution is
  not yet enabled for imports)

All imported source is kept under `POLYGLOT_DATA_ROOT` and is never executed.
The ZIP service rejects absolute paths, `..` traversal, symlinks, excessive
file counts, oversized files, and extraction quota violations. GitHub imports
only accept HTTPS `github.com` URLs or `owner/repository` references. A
server-side `GITHUB_TOKEN` can authorize private repository downloads without
exposing a token to the browser.

## Stage 1 API and providers

- `POST /api/v1/translate` accepts source/target languages, provider, model,
  mode, generation controls, and an explanation flag.
- `GET /health` and `GET /ready` provide service checks.
- `GET /api/v1/history` and `DELETE /api/v1/history/{id}` manage translation
  history.
- OpenAPI is available at `http://localhost:8000/docs`.

## Validation

```powershell
npm run lint
npm run typecheck
npm run build
cd backend
pytest
```

## Honest Stage 2 boundaries

The current foundation uses SQLite and an in-process API. PostgreSQL/Alembic,
real user authentication, Redis/Celery workers, SSE job progress, S3 artifact
storage, private GitHub OAuth/App installation, and multi-user authorization
are not claimed as complete yet. The domain tables and interfaces leave room
for those integrations without changing the source snapshot contract. Stage 3
AI orchestration has not been started.
