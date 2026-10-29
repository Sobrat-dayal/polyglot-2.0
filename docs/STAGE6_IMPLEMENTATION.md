# Stage 6: Transmute baseline

Transmute is a reviewable transformation boundary, not a claim of universal
semantic conversion. The current implementation performs bounded deterministic
rewrites and records every result, warning, mapping, hash, validation status,
and review decision.

## Implemented transformations

- JavaScript to TypeScript:
  - Literal string and number annotations in type-safe mode
  - CommonJS `module.exports` to default export
  - Delimiter validation
- Python to JavaScript:
  - Basic function, conditional, loop, boolean, null, and print rewrites
  - Async function declaration rewrite
  - Python AST parse diagnostics
- Same-language modernization/refactoring requests are review-only and do not
  silently mutate code.
- Unsupported pairs return the original source with an explicit unsupported
  warning; they are never presented as successful conversion.

## API

- `GET /api/v1/transmute/languages`
- `GET /api/v1/transmute/capabilities`
- `POST /api/v1/transmute/translate`
- `POST /api/v1/projects/{id}/transmute/files`
- `POST /api/v1/projects/{id}/transmute/modules`
- `GET /api/v1/transmute/results/{id}`
- `GET /api/v1/transmute/results/{id}/diff`
- `GET /api/v1/transmute/results/{id}/validation`
- `POST /api/v1/transmute/results/{id}/approve`
- `POST /api/v1/transmute/results/{id}/reject`
- `GET /api/v1/transmute/history`

Project file and module endpoints read immutable authorized snapshots and
reject traversal. Results are persisted with source/generated SHA-256 hashes
and source paths.

## Explicit boundaries

This stage does not execute generated code, install dependencies, run arbitrary
repository scripts, or claim behavioral equivalence. Cross-file imports are
preserved but unresolved references are surfaced for review. Framework recipes,
full semantic conversion, compiler execution, automated repair, and isolated
test execution remain future work. Neural Core remains available through the
existing translation endpoint; Transmute deterministic adapters do not contain
provider-specific code.
