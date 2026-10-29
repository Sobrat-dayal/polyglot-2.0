"""StackForge catalog, typed target architecture, and deterministic planning.

The registry is deliberately separate from migration support: a technology can
be compatible with another technology without Polyglot having a verified
transformation recipe for it.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

STACK_SCHEMA_VERSION = "stackforge-1.0"


class Technology(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    category: str
    ecosystem: str
    versions: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    compatible_with: list[str] = Field(default_factory=list)
    deprecated: bool = False
    migration_support: Literal["verified", "experimental", "planned", "unsupported", "unknown"] = "unknown"
    documentation_url: str | None = None
    verified_at: str | None = None


class Service(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(default="", max_length=500)
    language: str
    framework: str
    runtime_version: str | None = None
    api_protocol: str | None = None
    database_ids: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    deployment_unit: str = "container"


class Database(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    engine: str
    version: str | None = None
    orm: str | None = None
    migration_tool: str | None = None


class Frontend(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default="web", max_length=80)
    framework: str = "nextjs"
    language: str = "typescript"
    rendering: str = "hybrid"
    state_management: str | None = None
    styling: str | None = None
    package_manager: str | None = None


class Requirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    priorities: list[str] = Field(default_factory=list)
    security_constraints: list[str] = Field(default_factory=list)
    compliance: list[str] = Field(default_factory=list)
    preserve_behavior: bool = True
    strict_types: bool = False
    test_categories: list[str] = Field(default_factory=list)


class TargetStack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = STACK_SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=120)
    source_analysis_id: str | None = None
    architecture: str = "modular_monolith"
    frontends: list[Frontend] = Field(default_factory=list)
    services: list[Service] = Field(default_factory=list)
    databases: list[Database] = Field(default_factory=list)
    authentication: dict[str, Any] = Field(default_factory=dict)
    infrastructure: dict[str, Any] = Field(default_factory=dict)
    requirements: Requirements = Field(default_factory=Requirements)
    extensions: dict[str, Any] = Field(default_factory=dict)


class CompatibilityIssue(BaseModel):
    issue_id: str
    state: Literal["compatible", "conditionally_compatible", "incompatible", "unknown"]
    severity: Literal["info", "warning", "error"]
    affected_components: list[str]
    explanation: str
    constraints: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    requires_decision: bool = False
    source: str = "deterministic-stackforge-rule"
    validated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    category: str
    source: str
    target: str
    version: str
    status: Literal["verified", "experimental", "planned", "unsupported", "unknown"]
    prerequisites: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    risk_categories: list[str] = Field(default_factory=list)


TECHNOLOGIES = [
    Technology(id="python", name="Python", category="language", ecosystem="python", versions=["3.11", "3.12", "3.13"], migration_support="experimental"),
    Technology(id="javascript", name="JavaScript", category="language", ecosystem="javascript", versions=["ES2022", "ES2024"], migration_support="experimental"),
    Technology(id="typescript", name="TypeScript", category="language", ecosystem="javascript", versions=["5.4", "5.5"], migration_support="experimental"),
    Technology(id="go", name="Go", category="language", ecosystem="go", versions=["1.22", "1.23"], migration_support="planned"),
    Technology(id="rust", name="Rust", category="language", ecosystem="rust", versions=["1.78", "1.80"], migration_support="planned"),
    Technology(id="java", name="Java", category="language", ecosystem="jvm", versions=["17", "21"], migration_support="unknown"),
    Technology(id="csharp", name="C#", category="language", ecosystem="dotnet", versions=["12"], migration_support="unknown"),
    Technology(id="react", name="React", category="frontend_framework", ecosystem="javascript", versions=["18", "19"], languages=["javascript", "typescript"], migration_support="experimental"),
    Technology(id="nextjs", name="Next.js", category="frontend_framework", ecosystem="javascript", versions=["14", "15"], languages=["javascript", "typescript"], compatible_with=["react", "typescript", "javascript"], migration_support="experimental"),
    Technology(id="vue", name="Vue", category="frontend_framework", ecosystem="javascript", versions=["3"], languages=["javascript", "typescript"], migration_support="unknown"),
    Technology(id="fastapi", name="FastAPI", category="backend_framework", ecosystem="python", versions=["0.110", "0.115"], languages=["python"], compatible_with=["python", "postgresql", "sqlalchemy"], migration_support="experimental"),
    Technology(id="django", name="Django", category="backend_framework", ecosystem="python", versions=["4.2", "5.1"], languages=["python"], compatible_with=["python", "postgresql", "django-orm"], migration_support="planned"),
    Technology(id="express", name="Express", category="backend_framework", ecosystem="javascript", versions=["4", "5"], languages=["javascript", "typescript"], compatible_with=["javascript", "typescript", "mongodb", "postgresql"], migration_support="experimental"),
    Technology(id="nestjs", name="NestJS", category="backend_framework", ecosystem="javascript", versions=["10", "11"], languages=["typescript"], compatible_with=["typescript", "postgresql", "prisma"], migration_support="planned"),
    Technology(id="spring-boot", name="Spring Boot", category="backend_framework", ecosystem="jvm", versions=["3"], languages=["java"], migration_support="unknown"),
    Technology(id="postgresql", name="PostgreSQL", category="database", ecosystem="sql", versions=["14", "15", "16"], compatible_with=["python", "typescript", "java", "fastapi", "express", "sqlalchemy", "prisma"], migration_support="experimental"),
    Technology(id="mysql", name="MySQL", category="database", ecosystem="sql", versions=["8"], migration_support="unknown"),
    Technology(id="mongodb", name="MongoDB", category="database", ecosystem="nosql", versions=["6", "7"], compatible_with=["javascript", "typescript", "express", "mongoose"], migration_support="experimental"),
    Technology(id="redis", name="Redis", category="cache", ecosystem="redis", versions=["7"], migration_support="unknown"),
    Technology(id="sqlalchemy", name="SQLAlchemy", category="orm", ecosystem="python", versions=["2"], languages=["python"], compatible_with=["python", "postgresql", "mysql"], migration_support="experimental"),
    Technology(id="prisma", name="Prisma", category="orm", ecosystem="javascript", versions=["5"], languages=["javascript", "typescript"], compatible_with=["typescript", "postgresql", "mysql", "mongodb"], migration_support="planned"),
    Technology(id="django-orm", name="Django ORM", category="orm", ecosystem="python", versions=["5"], languages=["python"], compatible_with=["python", "postgresql", "mysql"], migration_support="planned"),
    Technology(id="rest", name="REST", category="api", ecosystem="web", versions=["HTTP"], migration_support="experimental"),
    Technology(id="graphql", name="GraphQL", category="api", ecosystem="web", versions=["2024"], migration_support="planned"),
    Technology(id="grpc", name="gRPC", category="api", ecosystem="rpc", versions=["1"], migration_support="planned"),
    Technology(id="docker", name="Docker", category="deployment", ecosystem="containers", versions=["24", "25"], migration_support="experimental"),
    Technology(id="kubernetes", name="Kubernetes", category="deployment", ecosystem="containers", versions=["1.29", "1.30"], migration_support="planned"),
    Technology(id="tailwind", name="Tailwind CSS", category="styling", ecosystem="javascript", versions=["3", "4"], compatible_with=["react", "nextjs", "vue"], migration_support="planned"),
    Technology(id="redux-toolkit", name="Redux Toolkit", category="state", ecosystem="javascript", versions=["2"], compatible_with=["react", "nextjs"], migration_support="unknown"),
]

RECIPES = [
    Recipe(id="js-to-ts", name="JavaScript to TypeScript", category="language", source="javascript", target="typescript", version="1.0", status="experimental", steps=["Inventory dynamic values", "Add type configuration", "Convert modules incrementally", "Run type-checking and differential tests"], limitations=["Runtime behavior is not proven equivalent"], risk_categories=["dynamic typing"]),
    Recipe(id="rest-to-graphql", name="REST to GraphQL planning", category="api", source="rest", target="graphql", version="1.0", status="planned", steps=["Map endpoints to schema operations", "Define pagination and error contracts", "Update clients"], limitations=["Resolver implementation is deferred"], risk_categories=["contract change"]),
    Recipe(id="mongodb-to-postgresql", name="MongoDB to PostgreSQL planning", category="database", source="mongodb", target="postgresql", version="1.0", status="experimental", steps=["Extract source models", "Map types and indexes", "Design transfer and rollback", "Validate consistency"], limitations=["Data migration execution is deferred"], risk_categories=["schema mismatch"]),
    Recipe(id="compose-to-kubernetes", name="Docker Compose to Kubernetes planning", category="infrastructure", source="docker", target="kubernetes", version="1.0", status="planned", steps=["Map services and volumes", "Define probes and resources", "Review secrets and ingress"], limitations=["Infrastructure generation is deferred"], risk_categories=["deployment"]),
]


def catalog(query: str | None = None, category: str | None = None, ecosystem: str | None = None) -> list[Technology]:
    values = TECHNOLOGIES
    if query:
        needle = query.casefold()
        values = [item for item in values if needle in f"{item.id} {item.name} {item.category}".casefold()]
    if category:
        values = [item for item in values if item.category == category]
    if ecosystem:
        values = [item for item in values if item.ecosystem == ecosystem]
    return values


def validate_stack(stack: TargetStack) -> list[CompatibilityIssue]:
    issues: list[CompatibilityIssue] = []
    known = {item.id: item for item in TECHNOLOGIES}
    for frontend in stack.frontends:
        framework = known.get(frontend.framework)
        if not framework:
            issues.append(CompatibilityIssue(issue_id=f"unknown-frontend-{frontend.id}", state="unknown", severity="warning", affected_components=[frontend.id], explanation=f"Frontend technology '{frontend.framework}' is not in the verified catalog.", requires_decision=True))
        elif framework.languages and frontend.language not in framework.languages:
            issues.append(CompatibilityIssue(issue_id=f"frontend-language-{frontend.id}", state="incompatible", severity="error", affected_components=[frontend.id, frontend.language], explanation=f"{framework.name} does not list {frontend.language} as a supported language.", alternatives=framework.languages, requires_decision=True))
        if frontend.rendering == "server_side" and frontend.framework in {"react", "vue"}:
            issues.append(CompatibilityIssue(issue_id=f"rendering-{frontend.id}", state="conditionally_compatible", severity="warning", affected_components=[frontend.id], explanation=f"Server-side rendering requires a framework runtime such as Next.js or Nuxt, not the library alone.", alternatives=["nextjs"]))
    service_ids = {service.id for service in stack.services}
    for service in stack.services:
        framework = known.get(service.framework)
        if framework and framework.languages and service.language not in framework.languages:
            issues.append(CompatibilityIssue(issue_id=f"service-language-{service.id}", state="incompatible", severity="error", affected_components=[service.id, service.framework], explanation=f"{framework.name} requires one of: {', '.join(framework.languages)}.", alternatives=framework.languages, requires_decision=True))
        for dependency in service.depends_on:
            if dependency not in service_ids:
                issues.append(CompatibilityIssue(issue_id=f"missing-service-{service.id}-{dependency}", state="incompatible", severity="error", affected_components=[service.id, dependency], explanation="Service dependency does not resolve to a configured service.", requires_decision=True))
        for database_id in service.database_ids:
            if database_id not in {database.id for database in stack.databases}:
                issues.append(CompatibilityIssue(issue_id=f"missing-database-{service.id}-{database_id}", state="incompatible", severity="error", affected_components=[service.id, database_id], explanation="Service references an undefined database.", requires_decision=True))
    for database in stack.databases:
        if database.orm:
            orm = known.get(database.orm)
            if orm and orm.languages and not any(service.language in orm.languages and database.id in service.database_ids for service in stack.services):
                issues.append(CompatibilityIssue(issue_id=f"orm-language-{database.id}", state="incompatible", severity="error", affected_components=[database.id, database.orm], explanation=f"{orm.name} cannot be the direct data-access layer for the configured service languages.", alternatives=orm.languages, requires_decision=True))
    if stack.architecture == "microservices" and len(stack.services) < 2:
        issues.append(CompatibilityIssue(issue_id="microservices-service-count", state="conditionally_compatible", severity="warning", affected_components=["architecture"], explanation="Microservices architecture requires at least two independently deployable services.", alternatives=["modular_monolith"], requires_decision=True))
    if stack.architecture == "event_driven" and not any(service.api_protocol in {"events", "message_queue"} for service in stack.services):
        issues.append(CompatibilityIssue(issue_id="event-transport-missing", state="incompatible", severity="error", affected_components=["architecture"], explanation="Event-driven architecture requires at least one event or message-queue interface.", requires_decision=True))
    return issues


def source_stack(analysis: dict[str, Any]) -> dict[str, Any]:
    languages = {}
    for file in analysis.get("languages", []):
        language = file.get("language")
        if language and language != "unknown":
            languages[language] = languages.get(language, 0) + 1
    return {
        "analysis_id": analysis.get("analysis_id"),
        "schema_version": analysis.get("ir", {}).get("schema_version", "project-ir-1.0"),
        "languages": [{"id": key, "file_count": value} for key, value in sorted(languages.items())],
        "technologies": analysis.get("stack", []) + analysis.get("architecture", []),
        "apis": analysis.get("apis", []),
        "dependencies": analysis.get("dependencies", []),
        "findings": analysis.get("findings", []),
    }


def resolve_plan(source: dict[str, Any], target: TargetStack, issues: list[CompatibilityIssue]) -> dict[str, Any]:
    source_ids = {item.get("language") for item in source.get("languages", [])}
    target_ids = {service.language for service in target.services}
    recipes = [recipe for recipe in RECIPES if recipe.source in source_ids and recipe.target in target_ids]
    if any(api.get("method") for api in source.get("apis", [])) and any(service.api_protocol == "graphql" for service in target.services):
        recipes.append(next(recipe for recipe in RECIPES if recipe.id == "rest-to-graphql"))
    steps = [{"id": "inventory", "title": "Freeze and verify source analysis snapshot", "depends_on": [], "status": "ready", "risk": "low", "requires_approval": False}]
    if target.authentication:
        steps.append({"id": "authentication", "title": "Review authentication and authorization mapping", "depends_on": ["inventory"], "status": "blocked", "risk": "high", "requires_approval": True})
    for recipe in recipes:
        steps.append({"id": recipe.id, "title": recipe.name, "depends_on": ["inventory"], "status": "blocked" if recipe.status in {"planned", "unsupported"} else "planned", "risk": "high" if recipe.risk_categories else "medium", "recipe_status": recipe.status, "limitations": recipe.limitations, "requires_approval": recipe.status != "verified"})
    steps.append({"id": "validation", "title": "Define differential, contract, security, and acceptance tests", "depends_on": [step["id"] for step in steps[1:]], "status": "planned", "risk": "medium", "requires_approval": False})
    approvals = [{"step_id": step["id"], "reason": "Non-verified recipe or security-sensitive architecture decision"} for step in steps if step.get("requires_approval")]
    return {"schema_version": "migration-plan-1.0", "source_analysis_id": target.source_analysis_id, "target_schema_version": target.schema_version, "steps": steps, "recipe_ids": [recipe.id for recipe in recipes], "unsupported": [issue.explanation for issue in issues if issue.state == "incompatible"], "required_approvals": approvals, "execution_readiness": "blocked" if approvals or any(issue.state == "incompatible" for issue in issues) else "review", "complexity": estimate_complexity(source, target, issues)}


def estimate_complexity(source: dict[str, Any], target: TargetStack, issues: list[CompatibilityIssue]) -> dict[str, Any]:
    drivers = []
    score = len(source.get("languages", [])) * 3 + len(source.get("dependencies", [])) + len(source.get("apis", [])) * 2 + len(target.services) * 5 + len(target.databases) * 4
    if source.get("findings"):
        score += len(source["findings"]) * 3
        drivers.append("static-analysis findings")
    if len(target.services) > 1:
        drivers.append("multiple target services")
    if any(issue.state == "incompatible" for issue in issues):
        score += 25
        drivers.append("blocking compatibility conflicts")
    score = min(100, max(0, score))
    return {"score": score, "level": "high" if score >= 60 else ("moderate" if score >= 25 else "low"), "drivers": drivers, "work_units": max(1, score // 5), "uncertainty": "relative only; human effort and provider cost are not estimated"}


def compare_architectures(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    def values(value: dict[str, Any]) -> dict[str, Any]:
        return {
            "architecture": value.get("architecture"),
            "languages": sorted(service.get("language") for service in value.get("services", [])),
            "frameworks": sorted(service.get("framework") for service in value.get("services", [])),
            "databases": sorted(database.get("engine") for database in value.get("databases", [])),
            "api_protocols": sorted(service.get("api_protocol") for service in value.get("services", []) if service.get("api_protocol")),
        }
    source, target = values(left), values(right)
    unchanged = [key for key in source if source[key] == target[key]]
    changed = [{"component": key, "from": source[key], "to": target[key]} for key in source if source[key] != target[key]]
    return {"unchanged": unchanged, "changed": changed, "human_decisions": [item["component"] for item in changed], "source": source, "target": target}


def advisor_prompt(source: dict[str, Any], target: TargetStack, issues: list[CompatibilityIssue]) -> str:
    return ("Act as a software architecture advisor. Use only this bounded evidence. "
            "Do not claim migration is implemented. Explain trade-offs and manual decisions.\n"
            f"Source: {source}\nTarget: {target.model_dump()}\nCompatibility: {[issue.model_dump() for issue in issues]}")
