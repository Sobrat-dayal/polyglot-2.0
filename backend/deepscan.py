"""Static, read-only project intelligence for DeepScan.

The engine intentionally reports parser coverage and uncertainty. It never
imports, executes, installs, or evaluates repository-controlled code.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

ANALYSIS_VERSION = "deepscan-1.0"
EXTENSIONS = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java",
    ".go": "go", ".rs": "rust", ".c": "c", ".h": "c",
    ".cpp": "c++", ".cc": "c++", ".cs": "c#", ".php": "php",
    ".rb": "ruby", ".kt": "kotlin", ".swift": "swift", ".dart": "dart",
    ".sql": "sql", ".html": "html", ".css": "css", ".scss": "scss",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".xml": "xml",
    ".sh": "shell",
}
MANIFESTS = {"package.json": "javascript", "pyproject.toml": "python", "requirements.txt": "python", "go.mod": "go", "Cargo.toml": "rust"}


@dataclass
class ScanResult:
    analysis_id: str
    project_id: str
    status: str
    languages: list[dict[str, Any]]
    stack: list[dict[str, Any]]
    symbols: list[dict[str, Any]]
    dependencies: list[dict[str, Any]]
    architecture: list[dict[str, Any]]
    apis: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    ir: dict[str, Any]
    diagnostics: list[dict[str, Any]]
    files_analyzed: int


def _span(node: ast.AST) -> dict[str, int | None]:
    return {
        "start_line": getattr(node, "lineno", None),
        "start_column": getattr(node, "col_offset", None),
        "end_line": getattr(node, "end_lineno", None),
        "end_column": getattr(node, "end_col_offset", None),
    }


def _entity(kind: str, name: str, path: str, language: str, span: dict[str, Any], evidence: str) -> dict[str, Any]:
    identifier = hashlib.sha256(f"{path}:{kind}:{name}:{span}".encode()).hexdigest()[:20]
    return {
        "id": identifier, "kind": kind, "name": name, "path": path,
        "language": language, "span": span, "evidence": evidence,
        "confidence": "verified", "analysis_version": ANALYSIS_VERSION,
    }


def detect_language(path: str, content: str) -> dict[str, Any]:
    suffix = Path(path).suffix.lower()
    language = EXTENSIONS.get(suffix)
    evidence = f"extension:{suffix}" if language else "content:unknown"
    if content.startswith("#!") and "python" in content.splitlines()[0]:
        language, evidence = "python", "shebang:python"
    if language in {"javascript", "typescript"} and re.search(r"\b(interface|type)\s+\w+", content):
        language, evidence = "typescript", "syntax:typescript-declaration"
    if not language and re.search(r"\b(def|import|from)\s+\w+", content):
        language, evidence = "python", "syntax:python-pattern"
    return {
        "path": path, "language": language or "unknown", "evidence": evidence,
        "parser_available": language in {"python", "javascript", "typescript"},
        "status": "detected" if language else "ambiguous",
        "confidence": "high" if language else "low",
    }


def _python_file(path: str, content: str, symbols: list[dict[str, Any]], dependencies: list[dict[str, Any]], diagnostics: list[dict[str, Any]], findings: list[dict[str, Any]], apis: list[dict[str, Any]]) -> None:
    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as error:
        diagnostics.append({"path": path, "severity": "error", "message": error.msg, "line": error.lineno, "confidence": "verified"})
        return
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(_entity("function" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "class", node.name, path, "python", _span(node), "python.ast"))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            for name in names:
                dependencies.append({"from": path, "to": name, "kind": "imports", "evidence": "python.ast", "confidence": "verified"})
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"get", "post", "put", "patch", "delete"} and isinstance(node.func.value, ast.Name) and node.func.value.id in {"app", "router"}:
                apis.append({"method": node.func.attr.upper(), "path": "dynamic", "handler": path, "span": _span(node), "confidence": "inferred", "evidence": "python.ast"})
    if re.search(r"\b(eval|exec|__import__)\s*\(", content):
        findings.append({"rule_id": "PY-DYNAMIC-001", "category": "dynamic_behavior", "severity": "high", "message": "Dynamic code execution pattern detected; static analysis may be incomplete.", "path": path, "confidence": "verified", "span": {"start_line": 1}})
    for match in re.finditer(r"@(app|router)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)", content):
        apis.append({"method": match.group(2).upper(), "path": match.group(3), "handler": path, "span": {"start_line": content[:match.start()].count("\n") + 1}, "confidence": "verified", "evidence": "decorator"})


def _generic_file(path: str, language: str, content: str, symbols: list[dict[str, Any]], dependencies: list[dict[str, Any]], apis: list[dict[str, Any]]) -> None:
    for match in re.finditer(r"\b(?:function|class|interface|type|struct|func|fn)\s+([A-Za-z_$][\w$]*)", content):
        symbols.append(_entity("symbol", match.group(1), path, language, {"start_line": content[:match.start()].count("\n") + 1}, "conservative-regex"))
    for match in re.finditer(r"(?:import|require|from)\s*[({\"]?\s*[\"']?([^\"')\s]+)", content):
        dependencies.append({"from": path, "to": match.group(1), "kind": "imports", "evidence": "conservative-regex", "confidence": "inferred"})
    for match in re.finditer(r"\b(app|router)\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)", content):
        apis.append({"method": match.group(2).upper(), "path": match.group(3), "handler": path, "span": {"start_line": content[:match.start()].count("\n") + 1}, "confidence": "inferred", "evidence": "route-pattern"})


def analyze_snapshot(project_id: str, root: Path, analysis_id: str | None = None) -> ScanResult:
    analysis_id = analysis_id or str(uuid4())
    languages, stack, symbols, dependencies, architecture, apis, findings, diagnostics = [], [], [], [], [], [], [], []
    files_analyzed = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            diagnostics.append({"path": relative, "severity": "warning", "message": str(error), "confidence": "verified"})
            continue
        detection = detect_language(relative, content)
        languages.append(detection)
        if detection["language"] in {"python", "javascript", "typescript"}:
            files_analyzed += 1
            if detection["language"] == "python":
                _python_file(relative, content, symbols, dependencies, diagnostics, findings, apis)
            else:
                _generic_file(relative, detection["language"], content, symbols, dependencies, apis)
        elif detection["language"] != "unknown":
            files_analyzed += 1
        if Path(relative).name in MANIFESTS:
            stack.append({"name": Path(relative).name, "language": MANIFESTS[Path(relative).name], "path": relative, "confidence": "verified", "evidence": "manifest"})
    for item in stack:
        if item["name"] == "package.json":
            architecture.append({"component": "javascript-application", "evidence": item["path"], "confidence": "verified"})
        if item["name"] == "pyproject.toml":
            architecture.append({"component": "python-application", "evidence": item["path"], "confidence": "verified"})
    for dependency in dependencies:
        if dependency["to"].startswith(".") or "/" in dependency["to"]:
            continue
        dependency["kind"] = "external_or_unresolved"
        dependency["confidence"] = "inferred"
    graph_nodes = [{"id": item["path"], "kind": "file"} for item in languages]
    ir = {
        "schema_version": "project-ir-1.0", "analysis_id": analysis_id, "project_id": project_id,
        "entities": symbols, "relationships": dependencies, "source_files": languages,
        "extensions": {"apis": apis, "architecture": architecture},
    }
    return ScanResult(analysis_id, project_id, "completed", languages, stack, symbols, dependencies, architecture, apis, findings, ir, diagnostics, files_analyzed)


def markdown_report(result: ScanResult) -> str:
    return "\n".join([
        f"# DeepScan Report: {result.project_id}",
        f"- Analysis: `{result.analysis_id}`",
        f"- Version: `{ANALYSIS_VERSION}`",
        f"- Files analyzed: {result.files_analyzed}",
        f"- Symbols: {len(result.symbols)}",
        f"- Dependencies: {len(result.dependencies)}",
        f"- APIs: {len(result.apis)}",
        "",
        "## Languages",
        *[f"- `{item['path']}`: {item['language']} ({item['confidence']})" for item in result.languages],
        "",
        "## Findings",
        *[f"- **{item['severity']}** `{item['rule_id']}`: {item['message']} ({item['path']})" for item in result.findings],
        "",
        "## Limitations",
        "- Static analysis does not execute code and cannot resolve all dynamic imports, reflection, runtime dispatch, or generated code.",
    ])
