# Stage 9: Guardian baseline

Guardian provides an evidence-based verification boundary for migrated
projects. It intentionally reports unsupported dynamic operations instead of
executing untrusted source or generated code in the FastAPI process.

## Implemented

- Versioned `GuardianRequest` with mode, quality gates, privacy policy, limits,
  scenario inputs, and repair-attempt bounds.
- Authorization-protected persisted verification records and immutable evidence
  hashes.
- Static Python AST and JavaScript/TypeScript delimiter validation.
- Test discovery inventory for pytest, Jest/Vitest, Playwright, Go, and Rust.
- Deterministic supplied-observation comparison with explicit normalization
  rules and mismatch classification.
- Comprehensive reports that distinguish passed-within-scope, warnings, failed,
  inconclusive, and not-performed checks.
- Capability API and project-sidebar static verification control.

## API

- `POST /api/v1/projects/{id}/guardian`
- `GET /api/v1/guardian/verifications/{id}`
- `POST /api/v1/guardian/verifications/{id}/cancel`
- `POST /api/v1/guardian/static-validate`
- `GET /api/v1/guardian/capabilities`

## Safety boundary

No imported or generated code is executed. Dynamic application execution,
browser testing, database mutation testing, performance benchmarking, and
automated repair are marked unavailable until a hardened sandbox with
non-root execution, resource limits, filesystem isolation, network policy,
timeouts, and cleanup is deployed. A partial static result is never presented
as proof of application equivalence.
