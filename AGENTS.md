# Polyglot 2.0 Engineering Rules

- Keep the original `Polyglot` project unchanged; Stage 1 work belongs in this repository.
- Provider credentials are backend-only environment variables. Never log, return, or commit secrets.
- The canonical translation contract is `POST /api/v1/translate`; preserve explicit non-2xx errors.
- Keep provider integrations behind `backend/engine/translator.py` and mock them in automated tests.
- Run `npm run lint`, `npm run typecheck`, and `npm run build` for web changes.
- Run `pytest` from `backend` for API changes.
- Do not claim syntax validation or live provider availability unless it was actually executed.
- Stage 2 project foundation is implemented in `backend/foundation.py`; keep
  imported snapshots immutable and never execute imported project code.
- Treat ZIPs and GitHub repositories as untrusted. Enforce the extraction
  quotas and reject traversal, symlink, and absolute paths.
- Protected project routes must verify workspace ownership before adding
  authentication identities; guest mode currently uses the isolated guest
  workspace.
