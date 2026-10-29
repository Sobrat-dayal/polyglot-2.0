"""Polyglot 2.0 canonical translation API.

The provider boundary is deliberately kept separate from FastAPI so providers
can be mocked in tests and additional OpenAI-compatible services can be added
without changing the HTTP contract.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import shutil
import time
import uuid
import zipfile
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, Request, Response, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.translator import (
    SUPPORTED_LANGUAGES,
    TranslationError,
    translate_with_provider,
)
from foundation import (
    ARTIFACT_ROOT,
    MAX_FILE_BYTES,
    create_import,
    ensure_guest_workspace,
    initialize_foundation,
    parse_github_reference,
)
from fastapi.responses import FileResponse
import httpx
from auth import create_session, current_user, password_hash, verify_password, read_session
from neural_core import AIError, AIRequest, AGENTS, NeuralGateway, run_agent
from deepscan import ANALYSIS_VERSION, analyze_snapshot, markdown_report
from stackforge import (
    RECIPES,
    STACK_SCHEMA_VERSION,
    TECHNOLOGIES,
    CompatibilityIssue,
    TargetStack,
    advisor_prompt,
    catalog,
    resolve_plan,
    source_stack,
    validate_stack,
)
from fastapi.responses import StreamingResponse

DATABASE_PATH = os.getenv("POLYGLOT_DATABASE_PATH", "polyglot.db")


class TranslationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_code: str = Field(min_length=1, max_length=500_000)
    source_language: str = Field(alias="source_lang", min_length=1)
    target_language: str = Field(alias="target_lang", min_length=1)
    provider: Literal["gemini", "nvidia", "groq", "ollama"] = "gemini"
    model: str | None = None
    mode: Literal[
        "standard", "idiomatic", "educational", "modernize",
        "type-safe", "performance-oriented"
    ] = "standard"
    strategy: Literal["manual", "fast", "economy", "quality", "balanced", "local_only"] = "manual"
    coding_preferences: str | None = Field(default=None, max_length=5_000)
    include_explanation: bool = True
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=4_096, ge=256, le=32_768)

    @field_validator("source_language", "target_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {value}")
        return normalized


class TranslationResponse(BaseModel):
    id: str
    generated_code: str
    source_language: str
    target_language: str
    provider: str
    model: str
    status: Literal["completed"]
    explanation: str | None
    warnings: list[str]
    validation: dict[str, Any]
    duration_ms: int
    token_usage: dict[str, int] | None = None


class HistoryItem(BaseModel):
    id: str
    source_language: str
    target_language: str
    provider: str
    model: str
    status: str
    created_at: str


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _init_database() -> None:
    with _connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS translations (
                id TEXT PRIMARY KEY,
                source_code TEXT NOT NULL,
                generated_code TEXT NOT NULL,
                source_language TEXT NOT NULL,
                target_language TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                explanation TEXT,
                warnings TEXT NOT NULL,
                validation TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        initialize_foundation(connection)
        ensure_guest_workspace(connection)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _init_database()
    yield


app = FastAPI(title="Polyglot 2.0 API", version="1.0.0", lifespan=lifespan)
neural_gateway = NeuralGateway()
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("POLYGLOT_ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "polyglot-api"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    try:
        with _connection() as connection:
            connection.execute("SELECT 1")
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Database is not ready") from error
    return {"status": "ready"}


@app.get("/api/v1/ai/providers")
async def ai_providers():
    return [
        {"name": name, "local": adapter.local, "configured": bool(getattr(adapter, "profiles", {"default": os.getenv("GEMINI_API_KEY", "")}).get("default", "")) or adapter.local}
        for name, adapter in neural_gateway.adapters.items()
    ]


@app.get("/api/v1/ai/models")
async def ai_models():
    models = await neural_gateway.router.catalog()
    return [model.__dict__ for model in models]


@app.get("/api/v1/ai/agents")
async def ai_agents():
    return [agent.model_dump() for agent in AGENTS.values()]


@app.post("/api/v1/ai/agents/{agent_id}/run")
async def ai_agent_run(agent_id: str, payload: dict[str, str]):
    try:
        return await run_agent(neural_gateway, agent_id, payload.get("content", ""), payload.get("strategy", "balanced"))
    except AIError as error:
        raise HTTPException(error.status_code, error.message) from error


def _project_context(connection: sqlite3.Connection, project_id: str | None, user_id: str, budget: int) -> list[dict[str, str]]:
    if not project_id:
        return []
    project = connection.execute("SELECT workspace_id,snapshot_path FROM projects WHERE id=?", (project_id,)).fetchone()
    if not project or not connection.execute(
        "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?", (project["workspace_id"], user_id)
    ).fetchone():
        raise HTTPException(403, "You do not have access to this project.")
    rows = connection.execute(
        "SELECT relative_path FROM project_files WHERE project_id=? AND selected=1 ORDER BY relative_path LIMIT 50",
        (project_id,),
    ).fetchall()
    context: list[dict[str, str]] = []
    used = 0
    root = Path(project["snapshot_path"]).resolve()
    for row in rows:
        target = (root / Path(*PurePosixPath(row["relative_path"]).parts)).resolve()
        if root not in target.parents or not target.is_file() or target.stat().st_size > 200_000:
            continue
        content = target.read_text(encoding="utf-8", errors="replace")
        if used + len(content) > budget:
            break
        context.append({"role": "user", "content": f"Project file {row['relative_path']}:\n{content}"})
        used += len(content)
    return context


@app.post("/api/v1/ai/generate")
async def ai_generate(payload: AIRequest, request: Request):
    request_id = str(uuid.uuid4())
    actor = _actor(request)
    with _connection() as connection:
        context = _project_context(connection, payload.project_id, actor, payload.token_budget * 4)
    request.messages.extend(context)
    try:
        result = await neural_gateway.generate(payload, request_id)
    except AIError as error:
        with _connection() as connection:
            connection.execute(
                "INSERT INTO ai_requests(id,workspace_id,project_id,task_type,strategy,privacy_mode,status,routing,created_at,error) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (request_id, payload.workspace_id, payload.project_id, payload.task_type, payload.strategy, payload.privacy_mode, "failed", "{}", datetime.now(timezone.utc).isoformat(), error.message),
            )
        raise HTTPException(error.status_code, error.message) from error
    with _connection() as connection:
        connection.execute(
            """INSERT INTO ai_requests(id,workspace_id,project_id,task_type,provider,model,strategy,
            privacy_mode,status,input_tokens,output_tokens,total_tokens,duration_ms,estimated_cost,
            routing,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (result.request_id, payload.workspace_id, payload.project_id, payload.task_type, result.provider,
             result.model, payload.strategy, payload.privacy_mode, result.status, result.input_tokens,
             result.output_tokens, result.total_tokens, result.duration_ms, result.estimated_cost,
             json.dumps(result.routing), datetime.now(timezone.utc).isoformat()),
        )
    return result


@app.post("/api/v1/ai/stream")
async def ai_stream(payload: AIRequest, request: Request):
    request_id = str(uuid.uuid4())

    async def events():
        try:
            result = await neural_gateway.generate(payload, request_id)
            for index in range(0, len(result.content), 256):
                if await request.is_disconnected():
                    return
                chunk = result.content[index:index + 256].replace("\n", "\\n")
                yield f"event: token\ndata: {json.dumps({'text': chunk})}\n\n"
            yield f"event: complete\ndata: {result.model_dump_json()}\n\n"
        except AIError as error:
            yield f"event: error\ndata: {json.dumps({'detail': error.message})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/v1/ai/usage")
async def ai_usage(request: Request, limit: int = 100):
    actor = _actor(request)
    with _connection() as connection:
        rows = connection.execute(
            """SELECT r.* FROM ai_requests r LEFT JOIN projects p ON p.id=r.project_id
               LEFT JOIN workspace_members m ON m.workspace_id=COALESCE(r.workspace_id,p.workspace_id)
               WHERE m.user_id=? ORDER BY r.created_at DESC LIMIT ?""", (actor, min(max(limit, 1), 100))
        ).fetchall()
    return [dict(row) for row in rows]


def _authorized_project(connection: sqlite3.Connection, project_id: str, actor: str) -> sqlite3.Row:
    project = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    allowed = connection.execute(
        "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?",
        (project["workspace_id"], actor),
    ).fetchone() if project else None
    if not project or not allowed:
        raise HTTPException(404, "Project not found.")
    return project


@app.post("/api/v1/projects/{project_id}/analysis")
async def start_analysis(project_id: str, request: Request):
    with _connection() as connection:
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        project = _authorized_project(connection, project_id, actor)
    result = await asyncio.to_thread(analyze_snapshot, project_id, Path(project["snapshot_path"]))
    payload = {
        "analysis_id": result.analysis_id, "project_id": result.project_id,
        "status": result.status, "files_analyzed": result.files_analyzed,
        "symbols": len(result.symbols), "dependencies": len(result.dependencies),
        "apis": len(result.apis), "diagnostics": len(result.diagnostics),
    }
    with _connection() as connection:
        connection.execute(
            "INSERT INTO analyses VALUES(?,?,?,?,?,?,?)",
            (result.analysis_id, project_id, result.status, ANALYSIS_VERSION,
             result.files_analyzed, json.dumps(result.__dict__, default=lambda value: value.__dict__),
             datetime.now(timezone.utc).isoformat()),
        )
    return payload


def _analysis(analysis_id: str, request: Request | None = None) -> dict[str, Any]:
    with _connection() as connection:
        row = connection.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Analysis not found.")
    if request is not None:
        with _connection() as connection:
            actor = current_user(connection, request.cookies.get("polyglot_session"))
            _authorized_project(connection, row["project_id"], actor)
    return dict(row)


@app.get("/api/v1/projects/{project_id}/analysis")
async def list_analysis(project_id: str, request: Request):
    with _connection() as connection:
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        _authorized_project(connection, project_id, actor)
        rows = connection.execute("SELECT id,status,analysis_version,files_analyzed,created_at FROM analyses WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/v1/analysis/{analysis_id}/{section}")
async def analysis_section(analysis_id: str, section: str, request: Request):
    row = _analysis(analysis_id, request)
    result = json.loads(row["result_json"])
    sections = {
        "languages": result["languages"], "stack": result["stack"],
        "symbols": result["symbols"], "dependencies": result["dependencies"],
        "architecture": result["architecture"], "apis": result["apis"],
        "findings": result["findings"], "diagnostics": result["diagnostics"],
        "ir": result["ir"],
    }
    if section == "report":
        return {"markdown": markdown_report(type("Result", (), result)())}
    if section not in sections:
        raise HTTPException(404, "Unknown analysis section.")
    return {"analysis_id": analysis_id, "section": section, "items": sections[section]}


@app.post("/api/v1/projects/{project_id}/code-search")
async def code_search(project_id: str, payload: dict[str, str], request: Request):
    query = payload.get("query", "").strip()
    if not query or len(query) > 200:
        raise HTTPException(422, "A bounded search query is required.")
    with _connection() as connection:
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        project = _authorized_project(connection, project_id, actor)
        files = connection.execute("SELECT relative_path FROM project_files WHERE project_id=? AND binary=0 LIMIT 2000", (project_id,)).fetchall()
    root = Path(project["snapshot_path"]).resolve()
    matches = []
    for row in files:
        target = (root / Path(*PurePosixPath(row["relative_path"]).parts)).resolve()
        if root not in target.parents:
            continue
        content = target.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(content.splitlines(), 1):
            if query.casefold() in line.casefold():
                matches.append({"path": row["relative_path"], "line": line_number, "text": line[:500]})
                if len(matches) >= 500:
                    return {"query": query, "matches": matches, "truncated": True}
    return {"query": query, "matches": matches, "truncated": False}


def _latest_analysis(connection: sqlite3.Connection, project_id: str, analysis_id: str | None = None) -> dict[str, Any]:
    row = connection.execute(
        "SELECT result_json FROM analyses WHERE project_id=? AND (? IS NULL OR id=?) ORDER BY created_at DESC LIMIT 1",
        (project_id, analysis_id, analysis_id),
    ).fetchone()
    if not row:
        raise HTTPException(409, "Run DeepScan for this project before configuring a target stack.")
    return json.loads(row["result_json"])


@app.get("/api/v1/stackforge/catalog")
async def stackforge_catalog(query: str | None = None, category: str | None = None, ecosystem: str | None = None):
    return {"items": [item.model_dump() for item in catalog(query, category, ecosystem)], "schema_version": STACK_SCHEMA_VERSION}


@app.get("/api/v1/stackforge/recipes")
async def stackforge_recipes(source: str | None = None, target: str | None = None):
    values = [item for item in RECIPES if (not source or item.source == source) and (not target or item.target == target)]
    return {"items": [item.model_dump() for item in values]}


@app.get("/api/v1/projects/{project_id}/stackforge/source")
async def stackforge_source(project_id: str, request: Request, analysis_id: str | None = None):
    with _connection() as connection:
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        _authorized_project(connection, project_id, actor)
        analysis = _latest_analysis(connection, project_id, analysis_id)
    return source_stack(analysis)


@app.post("/api/v1/projects/{project_id}/stackforge/validate")
async def stackforge_validate(project_id: str, target: TargetStack, request: Request):
    with _connection() as connection:
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        _authorized_project(connection, project_id, actor)
    issues = validate_stack(target)
    return {"schema_version": STACK_SCHEMA_VERSION, "state": "incompatible" if any(issue.state == "incompatible" for issue in issues) else ("conditionally_compatible" if issues else "compatible"), "issues": [issue.model_dump() for issue in issues]}


@app.post("/api/v1/projects/{project_id}/stackforge/configurations")
async def stackforge_create_configuration(project_id: str, target: TargetStack, request: Request):
    with _connection() as connection:
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        _authorized_project(connection, project_id, actor)
        analysis = _latest_analysis(connection, project_id, target.source_analysis_id)
        issues = validate_stack(target)
        version_row = connection.execute("SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM stackforge_configurations WHERE project_id=?", (project_id,)).fetchone()
        configuration_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO stackforge_configurations VALUES(?,?,?,?,?,?,?)",
            (configuration_id, project_id, int(version_row["next_version"]), STACK_SCHEMA_VERSION,
             analysis.get("analysis_id"), json.dumps(target.model_dump()),
             json.dumps([issue.model_dump() for issue in issues]), datetime.now(timezone.utc).isoformat()),
        )
    return {"id": configuration_id, "project_id": project_id, "version": int(version_row["next_version"]), "config": target.model_dump(), "compatibility": [issue.model_dump() for issue in issues]}


@app.get("/api/v1/projects/{project_id}/stackforge/configurations")
async def stackforge_list_configurations(project_id: str, request: Request):
    with _connection() as connection:
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        _authorized_project(connection, project_id, actor)
        rows = connection.execute("SELECT id,version,schema_version,source_analysis_id,created_at FROM stackforge_configurations WHERE project_id=? ORDER BY version DESC", (project_id,)).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/v1/stackforge/configurations/{configuration_id}")
async def stackforge_get_configuration(configuration_id: str, request: Request):
    with _connection() as connection:
        row = connection.execute("SELECT * FROM stackforge_configurations WHERE id=?", (configuration_id,)).fetchone()
        if not row:
            raise HTTPException(404, "StackForge configuration not found.")
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        _authorized_project(connection, row["project_id"], actor)
    return {**dict(row), "config": json.loads(row["config_json"]), "compatibility": json.loads(row["compatibility_json"])}


@app.get("/api/v1/stackforge/configurations/{configuration_id}/export")
async def stackforge_export_configuration(configuration_id: str, request: Request):
    value = await stackforge_get_configuration(configuration_id, request)
    return {"format": "polyglot-stackforge", "schema_version": STACK_SCHEMA_VERSION, "configuration": value["config"]}


@app.post("/api/v1/projects/{project_id}/stackforge/import")
async def stackforge_import_configuration(project_id: str, target: TargetStack, request: Request):
    return await stackforge_create_configuration(project_id, target, request)


@app.get("/api/v1/projects/{project_id}/stackforge/compare")
async def stackforge_compare_configurations(project_id: str, request: Request):
    with _connection() as connection:
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        _authorized_project(connection, project_id, actor)
        rows = connection.execute(
            "SELECT id,version,config_json,compatibility_json,created_at FROM stackforge_configurations WHERE project_id=? ORDER BY version DESC",
            (project_id,),
        ).fetchall()
    return {"items": [{
        "id": row["id"], "version": row["version"], "created_at": row["created_at"],
        "architecture": json.loads(row["config_json"]).get("architecture"),
        "service_count": len(json.loads(row["config_json"]).get("services", [])),
        "database_count": len(json.loads(row["config_json"]).get("databases", [])),
        "compatibility_state": "incompatible" if any(item["state"] == "incompatible" for item in json.loads(row["compatibility_json"])) else "review",
    } for row in rows]}


@app.post("/api/v1/stackforge/configurations/{configuration_id}/plan")
async def stackforge_create_plan(configuration_id: str, request: Request):
    with _connection() as connection:
        row = connection.execute("SELECT * FROM stackforge_configurations WHERE id=?", (configuration_id,)).fetchone()
        if not row:
            raise HTTPException(404, "StackForge configuration not found.")
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        _authorized_project(connection, row["project_id"], actor)
        target = TargetStack.model_validate(json.loads(row["config_json"]))
        analysis = _latest_analysis(connection, row["project_id"], target.source_analysis_id)
        plan = resolve_plan(source_stack(analysis), target, [CompatibilityIssue.model_validate(item) for item in json.loads(row["compatibility_json"])])
        plan_id = str(uuid.uuid4())
        connection.execute("INSERT INTO stackforge_plans VALUES(?,?,?,?)", (plan_id, configuration_id, json.dumps(plan), datetime.now(timezone.utc).isoformat()))
    return {"id": plan_id, **plan}


@app.get("/api/v1/stackforge/plans/{plan_id}")
async def stackforge_get_plan(plan_id: str, request: Request):
    with _connection() as connection:
        row = connection.execute(
            "SELECT p.*, c.project_id FROM stackforge_plans p JOIN stackforge_configurations c ON c.id=p.configuration_id WHERE p.id=?",
            (plan_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "StackForge plan not found.")
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        _authorized_project(connection, row["project_id"], actor)
    return {"id": plan_id, **json.loads(row["plan_json"])}


@app.post("/api/v1/projects/{project_id}/stackforge/advisor")
async def stackforge_advisor(project_id: str, target: TargetStack, request: Request):
    with _connection() as connection:
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        project = _authorized_project(connection, project_id, actor)
        analysis = _latest_analysis(connection, project_id, target.source_analysis_id)
    source = source_stack(analysis)
    issues = validate_stack(target)
    plan = resolve_plan(source, target, issues)
    try:
        response = await run_agent(
            neural_gateway, "documentation", advisor_prompt(source, target, issues), "balanced"
        )
        recommendation = response.content
        ai_metadata = {"provider": response.provider, "model": response.model, "duration_ms": response.duration_ms}
    except AIError as error:
        recommendation = "AI advisor unavailable; deterministic compatibility and planning results are shown."
        ai_metadata = {"status": "unavailable", "message": error.message}
    return {"project_id": project["id"], "recommendation": recommendation, "ai": ai_metadata, "compatibility": [issue.model_dump() for issue in issues], "plan_preview": plan}


@app.get("/api/v1/stackforge/presets")
async def stackforge_presets():
    return {"items": [
        {"id": "polyglot-web", "name": "Polyglot web baseline", "config": TargetStack(name="Polyglot web baseline", frontends=[{"framework": "nextjs", "language": "typescript", "rendering": "hybrid"}], services=[{"id": "api", "name": "API", "language": "python", "framework": "fastapi", "api_protocol": "rest"}], databases=[{"id": "primary", "engine": "postgresql", "orm": "sqlalchemy"}]).model_dump()},
        {"id": "typed-services", "name": "Typed service baseline", "config": TargetStack(name="Typed service baseline", architecture="modular_monolith", services=[{"id": "api", "name": "API", "language": "typescript", "framework": "nestjs", "api_protocol": "rest"}]).model_dump()},
    ]}


def _actor(request: Request) -> str:
    with _connection() as connection:
        return current_user(connection, request.cookies.get("polyglot_session"))


@app.post("/api/v1/auth/register")
async def register(payload: dict[str, str], response: Response):
    email = payload.get("email", "").strip().lower()
    try:
        hashed = password_hash(payload.get("password", ""))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if "@" not in email or len(email) > 254:
        raise HTTPException(422, "A valid email is required.")
    user_id = str(uuid.uuid4())
    with _connection() as connection:
        try:
            connection.execute("INSERT INTO users VALUES(?,?,?,?)", (user_id, email, hashed, datetime.now(timezone.utc).isoformat()))
            workspace_id = str(uuid.uuid4())
            connection.execute("INSERT INTO workspaces VALUES(?,?,?,?,?,0)", (workspace_id, "Personal workspace", "", user_id, datetime.now(timezone.utc).isoformat()))
            connection.execute("INSERT INTO workspace_members VALUES(?,?,?)", (workspace_id, user_id, "owner"))
            token = create_session(connection, user_id)
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, "An account with that email already exists.") from error
    response.set_cookie("polyglot_session", token, httponly=True, samesite="lax", secure=os.getenv("POLYGLOT_SECURE_COOKIES", "0") == "1", max_age=14 * 86400)
    return {"id": user_id, "email": email}


@app.post("/api/v1/auth/login")
async def login(payload: dict[str, str], response: Response):
    with _connection() as connection:
        row = connection.execute("SELECT id,password_hash FROM users WHERE email = ?", (payload.get("email", "").strip().lower(),)).fetchone()
        if not row or not verify_password(payload.get("password", ""), row["password_hash"]):
            raise HTTPException(401, "Invalid email or password.")
        token = create_session(connection, row["id"])
    response.set_cookie("polyglot_session", token, httponly=True, samesite="lax", secure=os.getenv("POLYGLOT_SECURE_COOKIES", "0") == "1", max_age=14 * 86400)
    return {"id": row["id"]}


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response):
    session_id = read_session(request.cookies.get("polyglot_session"))
    if session_id:
        with _connection() as connection:
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    response.delete_cookie("polyglot_session")


@app.get("/api/v1/workspaces")
async def list_workspaces(request: Request):
    actor = _actor(request)
    with _connection() as connection:
        rows = connection.execute(
            """SELECT w.id,w.name,w.description,w.owner_id,w.created_at,m.role
               FROM workspaces w JOIN workspace_members m ON m.workspace_id=w.id
               WHERE w.archived=0 AND m.user_id=?""", (actor,)
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/v1/workspaces")
async def create_workspace(payload: dict[str, str]):
    name = payload.get("name", "").strip()
    if not name or len(name) > 120:
        raise HTTPException(422, "Workspace name is required and must be under 120 characters.")
    workspace_id = str(uuid.uuid4())
    with _connection() as connection:
        connection.execute(
            "INSERT INTO workspaces(id,name,description,owner_id,created_at) VALUES(?,?,?,?,?)",
            (workspace_id, name, payload.get("description", "")[:1000], "guest", datetime.now(timezone.utc).isoformat()),
        )
        connection.execute("INSERT INTO workspace_members VALUES(?,?,?)", (workspace_id, "guest", "owner"))
    return {"id": workspace_id, "name": name, "role": "owner"}


@app.get("/api/v1/projects")
async def list_projects(request: Request, workspace_id: str | None = None, search: str | None = None):
    actor = _actor(request)
    query = """SELECT p.* FROM projects p JOIN workspace_members m
               ON m.workspace_id=p.workspace_id
               WHERE p.archived=0 AND m.user_id=?"""
    parameters: list[str] = [actor]
    if workspace_id:
        query += " AND workspace_id = ?"
        parameters.append(workspace_id)
    if search:
        query += " AND (name LIKE ? OR description LIKE ?)"
        parameters.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY updated_at DESC LIMIT 100"
    with _connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/v1/projects")
async def create_project(payload: dict[str, Any], request: Request):
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(422, "Project name is required.")
    with _connection() as connection:
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        workspace_id = payload.get("workspace_id")
        if not workspace_id:
            owned = connection.execute(
                "SELECT workspace_id FROM workspace_members WHERE user_id = ? ORDER BY rowid LIMIT 1",
                (actor,),
            ).fetchone()
            workspace_id = owned["workspace_id"] if owned else ensure_guest_workspace(connection)
        member = connection.execute(
            "SELECT role FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, actor),
        ).fetchone()
        if not member:
            raise HTTPException(403, "You do not have access to this workspace.")
        project_id = str(uuid.uuid4())
        timestamp = now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """INSERT INTO projects(id,workspace_id,name,description,tags,source_type,status,
            created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
            (project_id, workspace_id, name[:120], str(payload.get("description", ""))[:1000],
             json.dumps(payload.get("tags", [])), "blank", "ready", timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO activity VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), workspace_id, project_id, "project.created", "Created blank project", timestamp),
        )
    return {"id": project_id, "workspace_id": workspace_id, "name": name, "status": "ready"}


@app.post("/api/v1/projects/import/zip")
async def import_zip(request: Request, workspace_id: str | None = None, filename: str = "project.zip"):
    raw = await request.body()
    if not raw:
        raise HTTPException(400, "ZIP request body is empty.")
    with _connection() as connection:
        workspace = workspace_id or ensure_guest_workspace(connection)
        try:
            return create_import(connection, workspace, Path(filename).stem, "zip", raw, filename=filename)
        except (ValueError, zipfile.BadZipFile) as error:
            raise HTTPException(422, str(error)) from error


@app.post("/api/v1/projects/import/github")
async def import_github(payload: dict[str, str]):
    try:
        owner, repo = parse_github_reference(payload.get("repository", ""))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    branch = payload.get("branch") or "HEAD"
    url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
    try:
        headers = {}
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = "Bearer " + github_token
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise HTTPException(502, "GitHub repository could not be downloaded.") from error
    with _connection() as connection:
        workspace = payload.get("workspace_id") or ensure_guest_workspace(connection)
        try:
            return create_import(
                connection, workspace, repo, "github", response.content,
                source_url=f"https://github.com/{owner}/{repo}", branch=branch, filename=f"{repo}.zip",
            )
        except (ValueError, zipfile.BadZipFile) as error:
            raise HTTPException(422, str(error)) from error


@app.get("/api/v1/projects/{project_id}/files")
async def project_files(project_id: str, request: Request, search: str | None = None):
    query = "SELECT * FROM project_files WHERE project_id = ?"
    values: list[str] = [project_id]
    if search:
        query += " AND relative_path LIKE ?"
        values.append(f"%{search}%")
    query += " ORDER BY relative_path LIMIT 1000"
    with _connection() as connection:
        project = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        allowed = connection.execute(
            "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?",
            (project["workspace_id"], actor),
        ).fetchone() if project else None
        if not project or not allowed:
            raise HTTPException(404, "Project not found.")
        rows = connection.execute(query, values).fetchall()
    return {"project": dict(project), "files": [dict(row) for row in rows]}


@app.patch("/api/v1/projects/{project_id}")
async def update_project(project_id: str, payload: dict[str, Any]):
    allowed = {"name", "description", "tags"}
    updates = {key: payload[key] for key in allowed if key in payload}
    if "name" in updates and not str(updates["name"]).strip():
        raise HTTPException(422, "Project name cannot be empty.")
    if not updates:
        raise HTTPException(422, "No project fields were supplied.")
    with _connection() as connection:
        project = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404, "Project not found.")
        values = []
        assignments = []
        for key, value in updates.items():
            assignments.append(f"{key} = ?")
            values.append(json.dumps(value) if key == "tags" else str(value)[:1000])
        values.extend([datetime.now(timezone.utc).isoformat(), project_id])
        connection.execute(
            f"UPDATE projects SET {', '.join(assignments)}, updated_at = ? WHERE id = ?", values
        )
        connection.execute(
            "INSERT INTO activity VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), project["workspace_id"], project_id, "project.updated",
             f"Updated {', '.join(updates)}", datetime.now(timezone.utc).isoformat()),
        )
        updated = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(updated)


@app.post("/api/v1/projects/{project_id}/archive")
async def archive_project(project_id: str, restore: bool = False):
    with _connection() as connection:
        project = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404, "Project not found.")
        archived = 0 if restore else 1
        connection.execute("UPDATE projects SET archived = ?, updated_at = ? WHERE id = ?",
                           (archived, datetime.now(timezone.utc).isoformat(), project_id))
        connection.execute(
            "INSERT INTO activity VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), project["workspace_id"], project_id,
             "project.restored" if restore else "project.archived",
             "Restored project" if restore else "Archived project",
             datetime.now(timezone.utc).isoformat()),
        )
    return {"id": project_id, "archived": bool(archived)}


@app.delete("/api/v1/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str):
    with _connection() as connection:
        project = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404, "Project not found.")
        connection.execute("DELETE FROM project_files WHERE project_id = ?", (project_id,))
        connection.execute("DELETE FROM activity WHERE project_id = ?", (project_id,))
        connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    shutil.rmtree(project["snapshot_path"], ignore_errors=True)


@app.get("/api/v1/projects/{project_id}/activity")
async def project_activity(project_id: str):
    with _connection() as connection:
        rows = connection.execute(
            "SELECT action,detail,created_at FROM activity WHERE project_id = ? ORDER BY created_at DESC LIMIT 100",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/v1/projects/{project_id}/files/{file_path:path}")
async def read_project_file(project_id: str, file_path: str, request: Request):
    with _connection() as connection:
        project = connection.execute("SELECT snapshot_path FROM projects WHERE id = ?", (project_id,)).fetchone()
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        allowed = connection.execute(
            "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?",
            (project["workspace_id"], actor),
        ).fetchone() if project else None
    if not project or not allowed:
        raise HTTPException(404, "Project not found.")
    root = Path(project["snapshot_path"]).resolve()
    target = (root / Path(*PurePosixPath(file_path).parts)).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(404, "File not found.")
    if target.stat().st_size > 2 * 1024 * 1024:
        raise HTTPException(413, "File is too large for preview.")
    return {"path": file_path, "content": target.read_text(encoding="utf-8", errors="replace")}


@app.post("/api/v1/projects/{project_id}/files/select")
async def select_project_files(project_id: str, payload: dict[str, list[str]]):
    paths = payload.get("paths", [])
    with _connection() as connection:
        project = connection.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404, "Project not found.")
        connection.execute("UPDATE project_files SET selected = 0 WHERE project_id = ?", (project_id,))
        connection.executemany(
            "UPDATE project_files SET selected = 1 WHERE project_id = ? AND relative_path = ?",
            [(project_id, path) for path in paths],
        )
    return {"selected": len(paths)}


@app.get("/api/v1/jobs")
async def list_jobs():
    with _connection() as connection:
        rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100").fetchall()
    return [dict(row) for row in rows]


@app.post("/api/v1/jobs")
async def create_job(payload: dict[str, Any], request: Request):
    job_type = payload.get("type", "").strip()
    if job_type not in {"index", "inventory"}:
        raise HTTPException(422, "Supported job types are index and inventory.")
    project_id = payload.get("project_id")
    key = payload.get("idempotency_key")
    with _connection() as connection:
        project = connection.execute("SELECT workspace_id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404, "Project not found.")
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        if not connection.execute("SELECT 1 FROM workspace_members WHERE workspace_id = ? AND user_id = ?", (project["workspace_id"], actor)).fetchone():
            raise HTTPException(403, "You do not have access to this project.")
        if key:
            existing = connection.execute("SELECT * FROM jobs WHERE idempotency_key = ?", (key,)).fetchone()
            if existing:
                return dict(existing)
        job_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO jobs(id,project_id,workspace_id,type,status,progress,current_step,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, project_id, project["workspace_id"], job_type, "queued", 0, "queued", key, timestamp),
        )
    asyncio.create_task(_run_job(job_id))
    return {"id": job_id, "status": "queued"}


async def _run_job(job_id: str):
    with _connection() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return
        connection.execute("UPDATE jobs SET status='running',started_at=?,current_step=?,progress=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), "processing", 10, job_id))
    await asyncio.sleep(0)
    with _connection() as connection:
        connection.execute("UPDATE jobs SET status='completed',progress=100,current_step=?,completed_at=? WHERE id=?", ("completed", datetime.now(timezone.utc).isoformat(), job_id))


@app.post("/api/v1/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    with _connection() as connection:
        cursor = connection.execute("UPDATE jobs SET status='cancelled',current_step='cancelled',completed_at=? WHERE id=? AND status IN ('queued','running')", (datetime.now(timezone.utc).isoformat(), job_id))
        if cursor.rowcount == 0:
            raise HTTPException(409, "Job cannot be cancelled in its current state.")
    return {"id": job_id, "status": "cancelled"}


@app.post("/api/v1/projects/{project_id}/artifacts")
async def upload_artifact(project_id: str, request: Request, file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > MAX_FILE_BYTES * 10:
        raise HTTPException(413, "Artifact is too large.")
    with _connection() as connection:
        project = connection.execute("SELECT workspace_id FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404, "Project not found.")
        actor = current_user(connection, request.cookies.get("polyglot_session"))
        if not connection.execute("SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?", (project["workspace_id"], actor)).fetchone():
            raise HTTPException(403, "You do not have access to this project.")
        artifact_id = str(uuid.uuid4())
        target = ARTIFACT_ROOT / artifact_id
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        digest = __import__("hashlib").sha256(raw).hexdigest()
        connection.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?)", (artifact_id, project_id, None, Path(file.filename or "artifact").name, str(target), len(raw), digest, datetime.now(timezone.utc).isoformat()))
    return {"id": artifact_id, "name": Path(file.filename or "artifact").name, "size_bytes": len(raw), "sha256": digest}


@app.get("/api/v1/projects/{project_id}/artifacts")
async def list_artifacts(project_id: str):
    with _connection() as connection:
        rows = connection.execute("SELECT id,name,size_bytes,sha256,created_at FROM artifacts WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/v1/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: str, request: Request):
    with _connection() as connection:
        artifact = connection.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if artifact:
            actor = current_user(connection, request.cookies.get("polyglot_session"))
            workspace = connection.execute(
                "SELECT workspace_id FROM projects WHERE id=?", (artifact["project_id"],)
            ).fetchone()
            if workspace:
                allowed = connection.execute(
                    "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?",
                    (workspace["workspace_id"], actor),
                ).fetchone()
            else:
                allowed = None
        else:
            allowed = None
    if not artifact or not allowed or not Path(artifact["path"]).is_file():
        raise HTTPException(404, "Artifact not found.")
    return FileResponse(artifact["path"], filename=artifact["name"], media_type="application/octet-stream")


@app.post("/api/v1/translate", response_model=TranslationResponse)
async def translate(payload: TranslationRequest, request: Request) -> TranslationResponse:
    started = time.perf_counter()
    translation_id = str(uuid.uuid4())
    try:
        if payload.strategy == "manual":
            result = await translate_with_provider(
                source_code=payload.source_code,
                source_language=payload.source_language,
                target_language=payload.target_language,
                provider_name=payload.provider,
                model=payload.model,
                mode=payload.mode,
                coding_preferences=payload.coding_preferences,
                include_explanation=payload.include_explanation,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                cancelled=lambda: await_request_cancelled(request),
            )
        else:
            gateway_result = await neural_gateway.generate(
                AIRequest(
                    task_type="code_translation",
                    provider=payload.provider,
                    model=payload.model,
                    strategy=payload.strategy,
                    privacy_mode="local_only" if payload.strategy == "local_only" else "cloud_allowed",
                    token_budget=payload.max_tokens,
                    messages=[{
                        "role": "user",
                        "content": f"Translate {payload.source_language} to {payload.target_language} in {payload.mode} mode. Return only code.\n{payload.source_code}",
                    }],
                ),
                translation_id,
            )
            from engine.translator import TranslationResult
            result = TranslationResult(
                code=gateway_result.content, provider=gateway_result.provider,
                model=gateway_result.model, explanation=None, warnings=[],
                validation={"status": "not_run"}, token_usage={
                    key: value for key, value in {
                        "prompt_tokens": gateway_result.input_tokens,
                        "completion_tokens": gateway_result.output_tokens,
                        "total_tokens": gateway_result.total_tokens,
                    }.items() if value is not None
                } or None,
            )
    except asyncio.CancelledError as error:
        raise HTTPException(status_code=499, detail="Translation request was cancelled") from error
    except TranslationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error

    duration_ms = int((time.perf_counter() - started) * 1000)
    created_at = datetime.now(timezone.utc).isoformat()
    with _connection() as connection:
        connection.execute(
            """INSERT INTO translations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                translation_id, payload.source_code, result.code,
                payload.source_language, payload.target_language,
                result.provider, result.model, "completed", result.explanation,
                str(result.warnings), str(result.validation), duration_ms, created_at,
            ),
        )
    return TranslationResponse(
        id=translation_id,
        generated_code=result.code,
        source_language=payload.source_language,
        target_language=payload.target_language,
        provider=result.provider,
        model=result.model,
        status="completed",
        explanation=result.explanation,
        warnings=result.warnings,
        validation=result.validation,
        duration_ms=duration_ms,
        token_usage=result.token_usage,
    )


async def await_request_cancelled(request: Request) -> bool:
    return await request.is_disconnected()


@app.get("/api/v1/history", response_model=list[HistoryItem])
async def history(limit: Annotated[int, Field(ge=1, le=100)] = 50):
    with _connection() as connection:
        rows = connection.execute(
            "SELECT id, source_language, target_language, provider, model, status, created_at "
            "FROM translations ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [HistoryItem(**dict(row)) for row in rows]


@app.delete("/api/v1/history/{translation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history(translation_id: str) -> None:
    with _connection() as connection:
        cursor = connection.execute("DELETE FROM translations WHERE id = ?", (translation_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Translation not found")


@app.post("/api/translate", response_model=TranslationResponse, include_in_schema=False)
async def legacy_translate(payload: TranslationRequest, request: Request):
    return await translate(payload, request)
