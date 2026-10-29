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
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.translator import (
    SUPPORTED_LANGUAGES,
    TranslationError,
    translate_with_provider,
)
from foundation import (
    ARTIFACT_ROOT,
    create_import,
    ensure_guest_workspace,
    initialize_foundation,
    parse_github_reference,
)
from fastapi.responses import FileResponse
import httpx

DATABASE_PATH = os.getenv("POLYGLOT_DATABASE_PATH", "polyglot.db")


class TranslationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_code: str = Field(min_length=1, max_length=500_000)
    source_language: str = Field(alias="source_lang", min_length=1)
    target_language: str = Field(alias="target_lang", min_length=1)
    provider: Literal["gemini", "nvidia", "groq"] = "gemini"
    model: str | None = None
    mode: Literal[
        "standard", "idiomatic", "educational", "modernize",
        "type-safe", "performance-oriented"
    ] = "standard"
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("POLYGLOT_ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
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


@app.get("/api/v1/workspaces")
async def list_workspaces():
    with _connection() as connection:
        rows = connection.execute(
            "SELECT id,name,description,owner_id,created_at FROM workspaces WHERE archived = 0"
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
async def list_projects(workspace_id: str | None = None, search: str | None = None):
    query = "SELECT * FROM projects WHERE archived = 0"
    parameters: list[str] = []
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
async def create_project(payload: dict[str, Any]):
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(422, "Project name is required.")
    with _connection() as connection:
        workspace_id = payload.get("workspace_id") or ensure_guest_workspace(connection)
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
            headers["Authorization"] = f"Bearer {github_token}"
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
async def project_files(project_id: str, search: str | None = None):
    query = "SELECT * FROM project_files WHERE project_id = ?"
    values: list[str] = [project_id]
    if search:
        query += " AND relative_path LIKE ?"
        values.append(f"%{search}%")
    query += " ORDER BY relative_path LIMIT 1000"
    with _connection() as connection:
        project = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
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
async def read_project_file(project_id: str, file_path: str):
    with _connection() as connection:
        project = connection.execute("SELECT snapshot_path FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not project:
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


@app.post("/api/v1/translate", response_model=TranslationResponse)
async def translate(payload: TranslationRequest, request: Request) -> TranslationResponse:
    started = time.perf_counter()
    translation_id = str(uuid.uuid4())
    try:
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
