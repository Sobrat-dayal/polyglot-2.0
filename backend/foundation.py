"""Stage 2 project, workspace, import, inventory, job, and artifact services."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from uuid import uuid4

MAX_ARCHIVE_BYTES = int(os.getenv("POLYGLOT_MAX_ARCHIVE_BYTES", str(100 * 1024 * 1024)))
MAX_EXTRACTED_BYTES = int(os.getenv("POLYGLOT_MAX_EXTRACTED_BYTES", str(500 * 1024 * 1024)))
MAX_FILES = int(os.getenv("POLYGLOT_MAX_FILES", "10000"))
MAX_FILE_BYTES = int(os.getenv("POLYGLOT_MAX_FILE_BYTES", str(10 * 1024 * 1024)))
DATA_ROOT = Path(os.getenv("POLYGLOT_DATA_ROOT", "polyglot-data")).resolve()
SNAPSHOT_ROOT = DATA_ROOT / "snapshots"
ARTIFACT_ROOT = DATA_ROOT / "artifacts"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_foundation(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS workspaces (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          owner_id TEXT NOT NULL, created_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS workspace_members (
          workspace_id TEXT NOT NULL, user_id TEXT NOT NULL, role TEXT NOT NULL,
          PRIMARY KEY (workspace_id, user_id), FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
          source_type TEXT NOT NULL, source_url TEXT, branch TEXT, commit_sha TEXT,
          status TEXT NOT NULL, snapshot_path TEXT, file_count INTEGER NOT NULL DEFAULT 0,
          total_bytes INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
        );
        CREATE TABLE IF NOT EXISTS project_files (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL, relative_path TEXT NOT NULL,
          size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, language TEXT, binary INTEGER NOT NULL,
          selected INTEGER NOT NULL DEFAULT 0, FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_files_path ON project_files(project_id, relative_path);
        CREATE INDEX IF NOT EXISTS idx_projects_workspace ON projects(workspace_id, archived, updated_at);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, project_id TEXT, workspace_id TEXT NOT NULL, type TEXT NOT NULL,
          status TEXT NOT NULL, progress INTEGER, current_step TEXT, error TEXT,
          idempotency_key TEXT UNIQUE, created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT,
          FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS artifacts (
          id TEXT PRIMARY KEY, project_id TEXT, job_id TEXT, name TEXT NOT NULL,
          path TEXT NOT NULL, size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL,
          created_at TEXT NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS activity (
          id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, project_id TEXT, action TEXT NOT NULL,
          detail TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """
    )
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)


def ensure_guest_workspace(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT id FROM workspaces WHERE owner_id = 'guest' LIMIT 1").fetchone()
    if row:
        return row[0]
    workspace_id = str(uuid4())
    connection.execute(
        "INSERT INTO workspaces(id,name,owner_id,created_at) VALUES(?,?,?,?)",
        (workspace_id, "Personal workspace", "guest", now()),
    )
    connection.execute(
        "INSERT INTO workspace_members VALUES(?,?,?)", (workspace_id, "guest", "owner")
    )
    return workspace_id


def safe_extract_zip(raw: bytes, destination: Path) -> list[tuple[str, bytes]]:
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds the configured upload limit.")
    entries: list[tuple[str, bytes]] = []
    extracted = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.infolist()) > MAX_FILES:
            raise ValueError("Archive contains too many files.")
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or not path.name:
                raise ValueError(f"Unsafe archive path: {info.filename}")
            if info.is_dir():
                continue
            if info.file_size > MAX_FILE_BYTES or extracted + info.file_size > MAX_EXTRACTED_BYTES:
                raise ValueError("Archive exceeds the configured extraction limit.")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError("Symbolic links are not allowed in imported archives.")
            content = archive.read(info)
            target = (destination / Path(*path.parts)).resolve()
            if destination.resolve() not in target.parents:
                raise ValueError(f"Unsafe archive path: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            entries.append((path.as_posix(), content))
            extracted += len(content)
    return entries


def inventory(connection: sqlite3.Connection, project_id: str, root: Path) -> tuple[int, int]:
    rows = []
    total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        if len(content) > MAX_FILE_BYTES:
            continue
        binary = 0 in content[:4096]
        extension = Path(relative).suffix.lower()
        language = {
            ".py": "python", ".js": "javascript", ".ts": "typescript", ".java": "java",
            ".go": "go", ".rs": "rust", ".php": "php", ".rb": "ruby", ".cs": "c#",
        }.get(extension)
        rows.append((str(uuid4()), project_id, relative, len(content),
                     hashlib.sha256(content).hexdigest(), language, int(binary)))
        total += len(content)
    connection.executemany(
        "INSERT INTO project_files(id,project_id,relative_path,size_bytes,sha256,language,binary) "
        "VALUES(?,?,?,?,?,?,?)", rows
    )
    return len(rows), total


def create_import(
    connection: sqlite3.Connection, workspace_id: str, name: str, source_type: str,
    raw: bytes, source_url: str | None = None, branch: str | None = None,
    commit_sha: str | None = None, filename: str = "project.zip",
) -> dict:
    project_id = str(uuid4())
    root = SNAPSHOT_ROOT / project_id
    root.mkdir(parents=True, exist_ok=False)
    try:
        files = safe_extract_zip(raw, root)
        file_count, total_bytes = inventory(connection, project_id, root)
        project = {
            "id": project_id, "workspace_id": workspace_id, "name": name[:120],
            "description": "", "tags": [], "source_type": source_type,
            "source_url": source_url, "branch": branch, "commit_sha": commit_sha,
            "status": "ready", "file_count": file_count, "total_bytes": total_bytes,
            "created_at": now(), "updated_at": now(), "archived": False,
        }
        connection.execute(
            """INSERT INTO projects(id,workspace_id,name,description,tags,source_type,source_url,
            branch,commit_sha,status,snapshot_path,file_count,total_bytes,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (project_id, workspace_id, project["name"], "", "[]", source_type, source_url,
             branch, commit_sha, "ready", str(root), file_count, total_bytes,
             project["created_at"], project["updated_at"]),
        )
        connection.execute(
            "INSERT INTO activity VALUES(?,?,?,?,?,?)",
            (str(uuid4()), workspace_id, project_id, "project.imported",
             f"Imported {filename} ({file_count} files)", now()),
        )
        return project
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        connection.execute("DELETE FROM project_files WHERE project_id = ?", (project_id,))
        raise


def parse_github_reference(reference: str) -> tuple[str, str]:
    value = reference.strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        owner, repo = value.split("/", 1)
    else:
        parsed = urlparse(value)
        if parsed.scheme not in {"https"} or parsed.netloc.lower() != "github.com":
            raise ValueError("Only HTTPS github.com repository URLs are supported.")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ValueError("GitHub reference must include owner and repository.")
        owner, repo = parts[:2]
    return owner, repo.removesuffix(".git")

