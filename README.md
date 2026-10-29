# Polyglot 2.0

Polyglot 2.0 is a developer-focused AI translation and project inspection
workspace. Stage 1 provides the Monaco translator and protected Gemini/NVIDIA
NIM/Groq adapters. Stage 2 adds persistent guest workspaces, project
management, immutable source snapshots, public/authorized GitHub imports,
safe ZIP imports, file inventory/search/selection, lifecycle actions, activity
history, password-based accounts, signed HttpOnly sessions, membership checks,
durable job records, local artifact storage, job cancellation, and a Neural
Core for provider-independent model discovery and routing.

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
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, and
  `POST /api/v1/auth/logout`
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
  plus `POST /api/v1/jobs` and `POST /api/v1/jobs/{id}/cancel`
- `POST /api/v1/projects/{id}/artifacts`, `GET /api/v1/projects/{id}/artifacts`,
  and authorized artifact download

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

## Stage 3 Neural Core

The backend exposes typed AI infrastructure at `/api/v1/ai`: provider status,
model discovery, bounded agent definitions, generation, and usage records.
NVIDIA NIM, Groq (including `GROQ_API_1_KEY` and `GROQ_API_2_KEY` profiles),
Gemini, and configurable local Ollama-compatible endpoints are supported.
Routing strategies include manual, fast, economy, quality, balanced, and
local-only. Local-only mode fails closed and never selects a cloud adapter.
See [docs/STAGE3_IMPLEMENTATION.md](docs/STAGE3_IMPLEMENTATION.md) for
capabilities, provider verification status, and deployment boundaries.

## Validation

```powershell
npm run lint
npm run typecheck
npm run build
cd backend
pytest
```

## Remaining infrastructure boundaries

The current deployment uses SQLite, local artifact storage, and an in-process
cooperative job runner. PostgreSQL/Alembic, Redis/Celery workers, SSE/WebSocket
progress, S3 storage, and private GitHub OAuth/App installation are not part of
the local implementation yet. Password authentication and workspace membership
authorization are implemented for the local API. Stage 3 AI orchestration has
not been started.
