# Stage 3 — Neural Core

## Implemented

The backend now contains a provider-agnostic Neural Core in
`backend/neural_core.py`:

- Typed `AIRequest` and `AIResponse` contracts.
- Provider adapter interface.
- NVIDIA NIM and Groq OpenAI-compatible adapters.
- Backward-compatible Gemini adapter.
- Ollama-compatible local adapter.
- Model discovery with observed availability states.
- Capability filtering.
- Manual, fast, economy, quality, balanced, and local-only routing.
- Explicit local-only privacy enforcement.
- Custom endpoint URL policy validation.
- Bounded project context retrieval from authorized selected files.
- Versioned task prompt templates.
- Bounded Code Reviewer, Security Reviewer, and Documentation agents.
- AI request/usage persistence with actual provider-reported token fields when available.

The existing translator can use the Neural Core by selecting a non-manual
routing strategy. Manual mode preserves the Stage 1 provider path.

## API

- `GET /api/v1/ai/providers`
- `GET /api/v1/ai/models`
- `GET /api/v1/ai/agents`
- `POST /api/v1/ai/agents/{agent_id}/run`
- `POST /api/v1/ai/generate`
- `POST /api/v1/ai/stream` (SSE transport with cancellation detection)
- `GET /api/v1/ai/usage`

## Provider status

| Provider | Implementation | Live verification |
|---|---|---|
| NVIDIA NIM | OpenAI-compatible generation and model discovery | Requires `NVIDIA_API_KEY` |
| Groq | OpenAI-compatible generation and model discovery; profile variables supported | Requires `GROQ_API_KEY`, `GROQ_API_1_KEY`, or `GROQ_API_2_KEY` |
| Gemini | GenAI generation and model discovery | Requires `GEMINI_API_KEY` |
| Ollama | Configurable local OpenAI-compatible endpoint | Requires a running configured Ollama server |

No live credentials or local inference server were available during CI
validation. Provider tests use deterministic fakes; live availability is never
claimed from those tests.

## Privacy and context

`local_only` filters the catalog to adapters marked local and fails closed if
none are accessible. It does not silently fall back to cloud providers.
Project context is limited to authorized, explicitly selected files and a
bounded character budget. Repository content remains untrusted prompt data.

## Known boundaries

The local deployment still uses SQLite and the Stage 2 in-process job runner.
Provider-native streaming, Redis/Celery execution, encrypted credential
storage, S3 artifacts, model benchmark suites, and full OAuth account
management remain deployment extensions rather than falsely completed features.
The SSE endpoint provides bounded gateway output chunks and completion/error
events; provider-native token streaming is not claimed for adapters that do not
expose it. No hidden model reasoning is stored or logged.
