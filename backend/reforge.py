"""Deterministic Reforge generators and validators.

These operations generate reviewable artifacts only. They never connect to
databases, deploy infrastructure, or handle raw credentials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReforgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    operation: Literal["database", "api", "infrastructure", "authentication", "consistency"]
    mode: Literal["analyze", "plan", "generate", "dry_run", "verify"] = "generate"
    source: str = Field(default="", max_length=500_000)
    target: str = Field(default="", max_length=100)
    require_approval: bool = True


def map_sql_types(sql: str, target: str = "postgresql") -> dict[str, Any]:
    mappings = {
        "INT": "INTEGER", "INTEGER": "INTEGER", "BIGINT": "BIGINT",
        "VARCHAR": "TEXT" if target == "postgresql" else "VARCHAR",
        "DATETIME": "TIMESTAMPTZ" if target == "postgresql" else "DATETIME",
        "BOOLEAN": "BOOLEAN", "TEXT": "TEXT", "FLOAT": "DOUBLE PRECISION" if target == "postgresql" else "FLOAT",
    }
    replacements = []
    for source_type, target_type in mappings.items():
        if re.search(rf"\b{source_type}\b", sql, re.IGNORECASE):
            replacements.append({"source": source_type, "target": target_type, "confidence": "deterministic"})
    transformed = sql
    for item in replacements:
        transformed = re.sub(rf"\b{item['source']}\b", item["target"], transformed, flags=re.IGNORECASE)
    return {"target": target, "sql": transformed, "mappings": replacements, "warnings": ["Review identifiers, indexes, constraints, and transaction semantics before execution."]}


def generate_graphql(rest: str) -> dict[str, Any]:
    routes = re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_{}:/.-]+)", rest, re.IGNORECASE)
    fields = []
    for method, path in routes:
        name = re.sub(r"[^A-Za-z0-9]+", "_", path.strip("/")).strip("_") or "root"
        operation = "query" if method.upper() == "GET" else "mutation"
        fields.append({"method": method.upper(), "path": path, "operation": operation, "field": name})
    schema = "\n".join(f"type Query {{ {item['field']}: JSON }}" if item["operation"] == "query" else f"type Mutation {{ {item['field']}: JSON }}" for item in fields)
    return {"protocol": "graphql", "routes": fields, "schema": schema or "scalar JSON\n type Query { health: JSON }", "warnings": ["Generated fields require resolver and input/output schema review."]}


def generate_openapi(rest: str) -> dict[str, Any]:
    routes = re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_{}:/.-]+)", rest, re.IGNORECASE)
    paths: dict[str, Any] = {}
    for method, path in routes:
        paths.setdefault(path, {})[method.lower()] = {"responses": {"200": {"description": "Successful response"}}}
    return {"openapi": "3.1.0", "info": {"title": "Generated API", "version": "0.1.0"}, "paths": paths, "warnings": ["Response schemas and authentication requirements require review."]}


def generate_kubernetes(compose: str) -> dict[str, Any]:
    services = re.findall(r"(?m)^\s{2}([A-Za-z0-9_-]+):\s*$", compose)
    manifests = []
    for service in services:
        manifests.append({
            "apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": service},
            "spec": {"selector": {"matchLabels": {"app": service}}, "template": {"metadata": {"labels": {"app": service}}, "spec": {"containers": [{"name": service, "image": f"{service}:latest"}]}}},
        })
    return {"services": services, "manifests": manifests, "warnings": ["Images, resources, probes, secrets, ingress, and persistent volumes require explicit review."]}


def inspect_secrets(content: str) -> list[dict[str, Any]]:
    patterns = [r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*[\"'][^\"']+[\"']", r"(?i)AKIA[0-9A-Z]{16}"]
    return [{"rule": "secret-reference", "line": content[:match.start()].count("\n") + 1, "message": "Potential embedded credential; use an environment or secret reference."} for pattern in patterns for match in re.finditer(pattern, content)]


def consistency_report(configuration: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
    issues = []
    services = {service.get("id") for service in configuration.get("services", [])}
    for service in generated.get("services", []):
        if service not in services:
            issues.append({"severity": "warning", "component": service, "message": "Generated infrastructure service is absent from target configuration."})
    issues.extend({"severity": "high", **finding} for finding in inspect_secrets(str(generated)))
    return {"status": "blocked" if any(item["severity"] == "high" for item in issues) else "review", "issues": issues}


def execute(request: ReforgeRequest) -> dict[str, Any]:
    if request.operation == "database":
        result = map_sql_types(request.source, request.target or "postgresql")
    elif request.operation == "api":
        result = generate_graphql(request.source) if request.target == "graphql" else generate_openapi(request.source)
    elif request.operation == "infrastructure":
        result = generate_kubernetes(request.source)
    elif request.operation == "authentication":
        result = {"strategy": request.target, "status": "review", "warnings": ["Authentication changes require controlled identity-provider and authorization tests."]}
    else:
        result = {"status": "review", "warnings": ["Provide generated component metadata for cross-stack reconciliation."]}
    result["operation"] = request.operation
    result["mode"] = request.mode
    result["approval_required"] = request.require_approval
    return result
