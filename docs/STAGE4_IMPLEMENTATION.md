# Stage 4: DeepScan baseline

DeepScan is a read-only, versioned project analysis surface. An analysis reads
the authorized project snapshot and persists a serialized Project IR; it never
imports, executes, installs, or evaluates repository code.

## Included

- Language detection by extension, shebang, and conservative syntax signals.
- Python `ast` extraction for functions, classes, imports, route decorators, and
  dynamic-execution diagnostics.
- Bounded lexical adapters for JavaScript and TypeScript symbols, imports, and
  route patterns.
- Manifest and architecture signals for common Python, JavaScript, Go, and Rust
  projects.
- Versioned entities, relationships, source files, APIs, architecture, and
  diagnostics in a Project IR.
- Persisted analyses with project-membership authorization.
- Language, stack, symbol, dependency, API, architecture, finding, diagnostic,
  IR, and Markdown report sections.
- Bounded case-insensitive project source search with snapshot path validation.

## API

- `POST /api/v1/projects/{project_id}/analysis`
- `GET /api/v1/projects/{project_id}/analysis`
- `GET /api/v1/analysis/{analysis_id}/{languages|stack|symbols|dependencies|architecture|apis|findings|diagnostics|ir|report}`
- `POST /api/v1/projects/{project_id}/code-search`

## Coverage and limitations

The current adapter is a dependable baseline, not a complete compiler-grade
semantic index. Dynamic imports, reflection, generated code, runtime dispatch,
untyped data flow, and framework-specific behavior may remain unresolved.
Results include evidence and confidence fields so consumers can distinguish
verified parser observations from inferred lexical signals. Tree-sitter and
native language servers remain future extensions.
