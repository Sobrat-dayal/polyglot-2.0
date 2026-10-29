"""Bounded deterministic transformations used by the Transmute stage."""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TRANSMUTE_VERSION = "transmute-1.0"
LANGUAGES = ("python", "javascript", "typescript", "java", "go", "rust")


class TransformRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    source_code: str = Field(min_length=1, max_length=500_000)
    source_language: str
    target_language: str
    mode: Literal["standard", "idiomatic", "educational", "type-safe", "performance-oriented", "modernize", "refactor"] = "standard"
    source_version: str | None = None
    target_version: str | None = None
    source_framework: str | None = None
    target_framework: str | None = None
    strategy: Literal["manual", "fast", "economy", "quality", "balanced", "local_only"] = "manual"
    run_validation: bool = Field(default=True, alias="validate")
    generate_tests: bool = False


@dataclass
class TransformResult:
    code: str
    status: str
    warnings: list[str]
    diagnostics: list[dict[str, Any]]
    mappings: list[dict[str, Any]]
    validation: dict[str, Any]
    recipe: str


def _mapping(source: str, target: str, reason: str) -> dict[str, Any]:
    return {"source": source, "target": target, "reason": reason, "confidence": "deterministic"}


def _python_to_javascript(source: str, mode: str) -> tuple[str, list[dict[str, Any]], list[str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return source, [], [f"Python parse failed: {error.msg} at line {error.lineno}"]
    mappings: list[dict[str, Any]] = []
    warnings: list[str] = []
    output = source
    replacements = [
        (r"\bNone\b", "null", "Python None to JavaScript null"),
        (r"\bTrue\b", "true", "Python True to JavaScript true"),
        (r"\bFalse\b", "false", "Python False to JavaScript false"),
        (r"\bprint\(", "console.log(", "Python print to console.log"),
    ]
    for pattern, replacement, reason in replacements:
        if re.search(pattern, output):
            output = re.sub(pattern, replacement, output)
            mappings.append(_mapping(pattern, replacement, reason))
    output = re.sub(r"\bdef\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*:", r"function \1(\2) {", output)
    output = re.sub(r"\belif\b", "else if", output)
    output = re.sub(r"\belse\s*:", "else {", output)
    output = re.sub(r"\bif\s+(.+):", r"if (\1) {", output)
    output = re.sub(r"\bfor\s+([A-Za-z_]\w*)\s+in\s+(.+):", r"for (const \1 of \2) {", output)
    if "def " in source:
        mappings.append(_mapping("def name(...):", "function name(...) {", "Python function declaration"))
    if re.search(r"\btry\s*:", source) or re.search(r"\bexcept\b", source):
        warnings.append("Exception syntax needs manual review; Python except semantics are not identical to JavaScript catch.")
    if re.search(r"\basync\s+def\b", source):
        output = re.sub(r"\basync\s+def\s+([A-Za-z_]\w*)\s*\(", r"async function \1(", output)
        mappings.append(_mapping("async def", "async function", "asynchronous function declaration"))
    if mode == "type-safe":
        warnings.append("Type annotations require semantic inference and were not fabricated.")
    if not isinstance(tree, ast.Module):
        warnings.append("Unsupported Python syntax was preserved for review.")
    return output, mappings, warnings


def _javascript_to_typescript(source: str, mode: str) -> tuple[str, list[dict[str, Any]], list[str]]:
    output = source
    mappings: list[dict[str, Any]] = []
    warnings: list[str] = []
    if re.search(r"\b(var|let|const)\s+\w+\s*=", source):
        mappings.append(_mapping("JavaScript variable declarations", "TypeScript variable declarations", "preserved runtime declaration"))
    if mode == "type-safe":
        output = re.sub(r"\b(const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([\"'])", r"\1 \2: string = \3", output)
        output = re.sub(r"\b(const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(\d+)", r"\1 \2: number = \3", output)
        mappings.append(_mapping("inferred string/number initializers", "explicit TypeScript annotations", "safe literal inference"))
    if re.search(r"\b(eval|Function)\s*\(", source):
        warnings.append("Dynamic JavaScript execution prevents reliable static typing.")
    if re.search(r"\bmodule\.exports\b", source):
        output = output.replace("module.exports", "export default")
        mappings.append(_mapping("module.exports", "export default", "CommonJS export rewrite"))
    return output, mappings, warnings


def validate_output(code: str, language: str) -> dict[str, Any]:
    if language == "python":
        try:
            ast.parse(code)
            return {"status": "passed", "level": "syntax", "parser": "python.ast"}
        except SyntaxError as error:
            return {"status": "failed", "level": "syntax", "parser": "python.ast", "message": error.msg, "line": error.lineno}
    if language in {"javascript", "typescript"}:
        balanced = all(code.count(opening) == code.count(closing) for opening, closing in [("{", "}"), ("(", ")"), ("[", "]")])
        return {"status": "passed" if balanced else "failed", "level": "lexical", "parser": "bounded-delimiter-check"}
    return {"status": "not_run", "level": "unsupported", "message": f"No local validator is configured for {language}."}


def transform(request: TransformRequest) -> TransformResult:
    source = request.source_language.lower()
    target = request.target_language.lower()
    if source == target and request.mode in {"modernize", "refactor"}:
        code = request.source_code
        mappings, warnings = [], ["Refactoring mode is limited to validation and traceable review in this release."]
        recipe = "same-language-review"
    elif source == "javascript" and target == "typescript":
        code, mappings, warnings = _javascript_to_typescript(request.source_code, request.mode)
        recipe = "javascript-to-typescript"
    elif source == "python" and target == "javascript":
        code, mappings, warnings = _python_to_javascript(request.source_code, request.mode)
        recipe = "python-to-javascript"
    else:
        code = request.source_code
        mappings, warnings = [], [f"No deterministic recipe is implemented for {source} to {target}; source was not modified."]
        recipe = "unsupported"
    validation = validate_output(code, target) if request.run_validation else {"status": "not_run", "level": "disabled"}
    diagnostics = [] if validation["status"] in {"passed", "not_run"} else [validation]
    status = "completed_with_validation" if validation["status"] == "passed" else ("completed_with_warnings" if validation["status"] == "not_run" else "partially_completed")
    return TransformResult(code, status, warnings, diagnostics, mappings, validation, recipe)


def unified_diff(source: str, target: str, source_name: str = "source", target_name: str = "generated") -> str:
    return "".join(difflib.unified_diff(source.splitlines(True), target.splitlines(True), fromfile=source_name, tofile=target_name))


def capabilities() -> list[dict[str, Any]]:
    return [
        {"source": "javascript", "target": "typescript", "status": "experimental", "constructs": ["declarations", "CommonJS default exports", "literal type inference"]},
        {"source": "python", "target": "javascript", "status": "experimental", "constructs": ["basic functions", "conditionals", "loops", "literal replacements"]},
        {"source": "*", "target": "*", "status": "unsupported", "constructs": [], "message": "Other pairs require Neural Core or a future verified adapter."},
    ]
