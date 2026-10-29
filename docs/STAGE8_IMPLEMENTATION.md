# Stage 8: Reforge baseline

Reforge adds deterministic, reviewable integration transformations for
database, API, authentication, and infrastructure boundaries. Operations are
persisted with an explicit execution mode and approval state.

## Implemented capabilities

- SQL type mapping for generated PostgreSQL/SQL-compatible DDL review.
- REST route inventory to GraphQL schema skeleton generation.
- REST route inventory to OpenAPI 3.1 document generation.
- Compose-shaped service-name extraction to Kubernetes Deployment manifests.
- Potential secret detection in generated metadata.
- Cross-stack consistency report primitives.
- Authentication migration analysis boundary with explicit planned status.
- Reforge operation persistence, workspace authorization, approval records, and
  capability metadata.
- Project-sidebar control for generating an approval-gated GraphQL contract.

## API

- `POST /api/v1/projects/{id}/reforge`
- `GET /api/v1/reforge/operations/{id}`
- `POST /api/v1/reforge/operations/{id}/approve`
- `GET /api/v1/reforge/capabilities`

## Safety and boundaries

The default behavior is non-destructive generation. Reforge does not connect to
live databases, extract production data, deploy Kubernetes resources, change
CI/CD repositories, migrate identities, or handle raw credentials. Database
dry-run requests are rejected until a disposable database adapter exists.
Generated schemas and manifests carry warnings and require review. Capability
status is separate from target-stack compatibility and does not imply runtime
or production verification.

These contracts are designed for Stage 9 Guardian validation: every operation
has request metadata, mode, result evidence, approval state, and explicit
limitations.
