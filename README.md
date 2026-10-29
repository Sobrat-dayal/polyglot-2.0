# Polyglot 2.0

Polyglot 2.0 is a developer-focused AI code translation workspace. Stage 1
provides a Next.js/Monaco client, a canonical typed FastAPI service, protected
Gemini/NVIDIA NIM/Groq adapters, and local SQLite translation history.

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
npm run dev
```

Open `http://localhost:3000`. Add at least one provider key to `.env` before
requesting a live translation. Keys are read only by the API process.

## API

- `GET /health` and `GET /ready` provide liveness/readiness checks.
- `POST /api/v1/translate` accepts source/target languages, provider, model,
  mode, generation controls, and an explanation flag.
- `GET /api/v1/history` lists saved translation metadata.
- `DELETE /api/v1/history/{id}` removes a saved translation.
- OpenAPI is available at `http://localhost:8000/docs`.

The API returns translated code in `generated_code`; provider failures are
non-2xx responses and are never rendered as translated source.

## Provider configuration

| Variable | Provider | Example model |
| --- | --- | --- |
| `GEMINI_API_KEY` | Google Gemini | `gemini-2.5-flash` |
| `NVIDIA_API_KEY` | NVIDIA NIM | `qwen/qwen2.5-coder-32b-instruct` |
| `GROQ_API_KEY` | Groq | `qwen/qwen3-32b` |

Model access depends on the account and provider. Live integrations are not
run in CI; the automated suite covers validation and service behavior without
requiring credentials.

## Validation

```powershell
npm run lint
npm run typecheck
npm run build
cd backend
pytest
```

Docker users can run `docker compose up --build` after creating `.env`.

## Architecture and limitations

The browser calls the Next.js server route, which proxies to FastAPI. FastAPI
validates the request, delegates to a provider adapter, and persists completed
metadata/code in SQLite. Provider credentials never cross that boundary.

Stage 1 intentionally does not claim whole-project migration, AST-equivalence
proof, language-specific formatting, accounts, or live model discovery. Those
are suitable follow-up work after the single-snippet contract is stable.
