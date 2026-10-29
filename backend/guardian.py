"""Evidence-based Guardian verification primitives.

Guardian deliberately does not execute imported or generated project code.
The current deployment has no hardened sandbox, so dynamic checks are reported
as not performed rather than being run in the API process.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


VERIFICATION_VERSION = "guardian-0.1"
MODES = (
    "code", "module", "framework", "full_project", "differential", "api",
    "database", "authentication", "ui", "security", "performance",
    "regression", "comprehensive", "repair_reverify", "ci",
)


class ResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    memory_mb: int = Field(default=256, ge=64, le=4096)
    process_limit: int = Field(default=32, ge=1, le=256)


class GuardianRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    migration_id: str | None = None
    target_artifact_id: str | None = None
    mode: Literal[
        "code", "module", "framework", "full_project", "differential", "api",
        "database", "authentication", "ui", "security", "performance",
        "regression", "comprehensive", "repair_reverify", "ci",
    ] = "comprehensive"
    selected_test_suites: list[str] = Field(default_factory=list, max_length=50)
    required_quality_gates: list[str] = Field(default_factory=lambda: ["static_validation"])
    privacy_policy: Literal["local_only", "allow_configured_providers"] = "local_only"
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    max_repair_attempts: int = Field(default=0, ge=0, le=3)
    scenarios: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def discover_tests(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inventory = []
    patterns = (
        ("pytest", re.compile(r"(^|/)(test_[^/]+|[^/]+_test)\.py$")),
        ("jest-vitest", re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")),
        ("playwright", re.compile(r"(^|/)(playwright|e2e)(/|$)", re.IGNORECASE)),
        ("go-test", re.compile(r"_test\.go$")),
        ("rust-test", re.compile(r"(^|/)tests?/")),
    )
    for file in files:
        path = str(file.get("relative_path", file.get("path", ""))).replace("\\", "/")
        for framework, pattern in patterns:
            if pattern.search(path):
                inventory.append({
                    "test_id": _digest({"framework": framework, "path": path})[:16],
                    "framework": framework,
                    "source_file": path,
                    "scope": "browser" if framework == "playwright" else "module",
                    "status": "discovered",
                    "execution": "not_performed_until_sandbox_validation",
                })
                break
    return inventory


def static_validate(source: str, language: str) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    normalized = language.lower()
    if normalized in {"python", "py"}:
        try:
            ast.parse(source)
        except SyntaxError as error:
            diagnostics.append({"severity": "error", "line": error.lineno, "column": error.offset, "message": error.msg})
    elif normalized in {"javascript", "typescript", "javascriptreact", "typescriptreact"}:
        pairs = {"(": ")", "[": "]", "{": "}"}
        stack: list[str] = []
        for index, character in enumerate(source):
            if character in pairs:
                stack.append(pairs[character])
            elif character in pairs.values():
                if not stack or stack.pop() != character:
                    diagnostics.append({"severity": "error", "offset": index, "message": "Unbalanced delimiter."})
                    break
        if stack:
            diagnostics.append({"severity": "error", "message": "Unclosed delimiter."})
    else:
        diagnostics.append({"severity": "info", "message": f"No compiler-grade validator configured for {language}."})
    return {"status": "failed" if any(item["severity"] == "error" for item in diagnostics) else "passed_with_warnings" if diagnostics else "passed", "diagnostics": diagnostics}


def _normalize(value: Any, rules: list[dict[str, Any]]) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(item, rules) for key, item in sorted(value.items()) if not any(rule.get("path") == key and rule.get("action") == "ignore" for rule in rules)}
    if isinstance(value, list):
        return [_normalize(item, rules) for item in value]
    return value


def compare_observations(source: Any, target: Any, rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    normalization = rules or []
    left = _normalize(source, normalization)
    right = _normalize(target, normalization)
    equal = left == right
    return {
        "status": "passed" if equal else "failed",
        "classification": "equivalent" if equal else "reproducible_mismatch",
        "source": left,
        "target": right,
        "normalization_rules": normalization,
        "evidence_hash": _digest({"source": left, "target": right, "rules": normalization}),
    }


def build_report(request: GuardianRequest, files: list[dict[str, Any]], observations: list[dict[str, Any]]) -> dict[str, Any]:
    tests = discover_tests(files)
    static_checks = [
        {"check": "test_discovery", "status": "passed", "count": len(tests)},
        {"check": "dynamic_execution", "status": "not_performed", "reason": "No hardened sandbox is configured; untrusted code must not execute in the API process."},
    ]
    checks = static_checks + observations
    failed = [check for check in checks if check.get("status") == "failed"]
    inconclusive = [check for check in checks if check.get("status") in {"not_performed", "inconclusive"}]
    status = "failed" if failed else "passed_with_warnings" if inconclusive else "passed_within_scope"
    return {
        "verification_version": VERIFICATION_VERSION,
        "mode": request.mode,
        "scope": "static_and_evidence_only",
        "status": status,
        "checks": checks,
        "tests": tests,
        "quality_gates": request.required_quality_gates,
        "limitations": ["Dynamic source/target execution, browser testing, database mutation testing, and performance measurement were not performed."],
        "created_at": _now(),
    }
