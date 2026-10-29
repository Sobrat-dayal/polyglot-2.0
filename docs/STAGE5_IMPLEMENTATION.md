# Stage 5: StackForge

StackForge provides a versioned target architecture model and migration
planning boundary. It separates deterministic technology compatibility from
Polyglot migration capability: a compatible pair can still have an
experimental, planned, or unsupported recipe.

## Delivered

- Typed, versioned target stack schema with frontends, heterogeneous backend
  services, databases, infrastructure, requirements, and extensions.
- Extensible backend technology catalog with categories, ecosystems, versions,
  language constraints, deprecation/support metadata, and documentation-ready
  fields.
- Versioned migration recipe registry with prerequisites, dependencies,
  limitations, risk categories, and explicit status.
- Deterministic compatibility engine for framework/language, ORM/language,
  service/database references, service dependency resolution, rendering,
  architecture, and event transport constraints.
- DeepScan source-stack projection tied to a specific analysis ID.
- Persisted configuration versions and migration plans in SQLite, with
  workspace authorization inherited from Foundation.
- Portable configuration export/import, configuration comparison, presets,
  recipe search, and plan previews.
- AI Architecture Advisor endpoint using the existing Neural Core
  `documentation` agent. If no provider is available, the API reports that
  condition and still returns deterministic findings rather than fabricating
  an AI answer.
- Sidebar target-stack configurator for language, framework, database,
  architecture validation, and version saving.

## API

- `GET /api/v1/stackforge/catalog`
- `GET /api/v1/stackforge/recipes`
- `GET /api/v1/stackforge/presets`
- `GET /api/v1/projects/{project_id}/stackforge/source`
- `POST /api/v1/projects/{project_id}/stackforge/validate`
- `POST /api/v1/projects/{project_id}/stackforge/configurations`
- `POST /api/v1/projects/{project_id}/stackforge/import`
- `GET /api/v1/projects/{project_id}/stackforge/configurations`
- `GET /api/v1/projects/{project_id}/stackforge/compare`
- `GET /api/v1/stackforge/configurations/{id}`
- `GET /api/v1/stackforge/configurations/{id}/export`
- `POST /api/v1/stackforge/configurations/{id}/plan`
- `GET /api/v1/stackforge/plans/{id}`
- `POST /api/v1/projects/{project_id}/stackforge/advisor`

## Boundaries

The Stage 5 implementation does not execute recipes, transform source code,
perform data migrations, generate infrastructure, or claim verified runtime
equivalence. Those operations remain later-stage work. Credentials are not
accepted in target configuration models; deployment settings are declarative.
Compatibility is deterministic and auditable, while AI output is advisory and
cannot override incompatibility findings.
