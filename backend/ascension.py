"""Stage 10 integration contracts: plugin manifests and platform capability audit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PLUGIN_API_VERSION = "1"
PLUGIN_CATEGORIES = {
    "language_adapter", "parser", "framework_detector", "ast_transform",
    "migration_recipe", "database_adapter", "api_adapter", "auth_adapter",
    "infrastructure_generator", "validator", "test_generator", "report_exporter",
}


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plugin_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
    author: str = Field(min_length=1, max_length=160)
    license: str = Field(default="UNLICENSED", max_length=80)
    polyglot_api_version: str = PLUGIN_API_VERSION
    category: str
    entry_point: str = Field(min_length=1, max_length=300)
    capabilities: list[str] = Field(default_factory=list, max_length=50)
    permissions: list[Literal["read_project", "write_artifacts", "network", "execute"]] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    supported_frameworks: list[str] = Field(default_factory=list)
    runtime_requirements: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    integrity_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        if value not in PLUGIN_CATEGORIES:
            raise ValueError(f"Unsupported plugin category: {value}")
        return value


def validate_manifest(document: dict[str, Any], *, existing_ids: set[str] | None = None) -> dict[str, Any]:
    manifest = PluginManifest.model_validate(document)
    if manifest.polyglot_api_version != PLUGIN_API_VERSION:
        raise ValueError(f"Plugin API version {manifest.polyglot_api_version} is incompatible with {PLUGIN_API_VERSION}.")
    if existing_ids and manifest.plugin_id in existing_ids:
        raise ValueError(f"Plugin ID is already registered: {manifest.plugin_id}")
    if "execute" in manifest.permissions:
        execution_status = "unsupported_without_isolation"
    else:
        execution_status = "review_required"
    return {"valid": True, "manifest": manifest.model_dump(), "execution_status": execution_status}


def manifest_checksum(document: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def platform_audit() -> dict[str, Any]:
    return {
        "stage": "10",
        "name": "Ascension",
        "release_status": "development",
        "items": [
            {"area": "translation", "status": "implemented", "evidence": "Stage 1 canonical API and provider adapters"},
            {"area": "project_workspaces", "status": "implemented", "evidence": "Foundation APIs with workspace authorization"},
            {"area": "migration", "status": "partial", "evidence": "Metamorphosis supports bounded deterministic transformations"},
            {"area": "reforge", "status": "partial", "evidence": "Approval-gated generation only; no live cutover"},
            {"area": "guardian", "status": "partial", "evidence": "Static/evidence verification; dynamic sandbox unavailable"},
            {"area": "github_delivery", "status": "partial", "evidence": "Import is implemented; branch/PR writes require explicit integration"},
            {"area": "cli", "status": "implemented", "evidence": "Cross-platform HTTP client included in repository"},
            {"area": "plugins", "status": "partial", "evidence": "Manifest validation and permission boundary; third-party execution disabled"},
            {"area": "production_readiness", "status": "not_ready", "evidence": "SQLite, local artifacts, and in-process jobs remain deployment boundaries"},
        ],
        "security_constraints": [
            "Never execute untrusted plugins in the trusted API process.",
            "Never expose provider credentials or CLI tokens in output.",
            "Never claim production readiness without deployment evidence.",
        ],
    }


def load_manifest(path: str) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Plugin manifest must be a JSON object.")
    return validate_manifest(document)
