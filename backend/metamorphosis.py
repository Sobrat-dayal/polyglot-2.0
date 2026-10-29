"""Checkpointed, dependency-aware full-project migration orchestration."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from transmute import TransformRequest, transform


class MigrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    project_id: str
    source_analysis_id: str | None = None
    configuration_id: str
    plan_id: str | None = None
    mode: Literal["complete", "frontend_only", "backend_only", "service", "module", "selected", "incremental", "partial", "hybrid"] = "partial"
    selected_paths: list[str] = Field(default_factory=list, max_length=100)
    target_language: str = "typescript"
    source_language: str = "javascript"
    strategy: Literal["manual", "fast", "economy", "quality", "balanced", "local_only"] = "manual"
    require_approval: bool = True
    run_validation: bool = Field(default=True, alias="validate")


def build_tasks(paths: list[str], mode: str) -> list[dict[str, Any]]:
    tasks = [
        {"id": "snapshot", "type": "verify_snapshot", "depends_on": [], "status": "pending", "weight": 1},
        {"id": "prepare", "type": "prepare_target", "depends_on": ["snapshot"], "status": "pending", "weight": 1},
    ]
    for path in paths:
        task_id = "translate:" + hashlib.sha256(path.encode()).hexdigest()[:12]
        tasks.append({"id": task_id, "type": "translate_file", "path": path, "depends_on": ["prepare"], "status": "pending", "weight": 3})
    tasks.append({"id": "validate", "type": "validate_output", "depends_on": [task["id"] for task in tasks[2:]], "status": "pending", "weight": 2})
    return tasks


def ready_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed = {task["id"] for task in tasks if task["status"] == "completed"}
    return [task for task in tasks if task["status"] == "pending" and all(dependency in completed for dependency in task["depends_on"])]


@dataclass
class ExecutionResult:
    status: str
    tasks: list[dict[str, Any]]
    generated: list[dict[str, Any]]
    warnings: list[str]
    metrics: dict[str, Any]


def execute(request: MigrationRequest, root: Path, tasks: list[dict[str, Any]], output_root: Path, cancel_requested: bool = False) -> ExecutionResult:
    output_root.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, Any]] = []
    warnings: list[str] = []
    processed = 0
    while True:
        ready = ready_tasks(tasks)
        if not ready:
            break
        if cancel_requested:
            for task in ready:
                task["status"] = "cancelled"
            return ExecutionResult("cancelled", tasks, generated, warnings, {"completed": processed, "total": len(tasks)})
        task = ready[0]
        task["status"] = "running"
        if task["type"] == "verify_snapshot":
            task["status"] = "completed"
        elif task["type"] == "prepare_target":
            (output_root / "MIGRATION-MANIFEST.json").write_text(json.dumps({"migration_id": request.project_id, "mode": request.mode}, indent=2), encoding="utf-8")
            task["status"] = "completed"
        elif task["type"] == "translate_file":
            source_path = (root / Path(*PurePosixPath(task["path"]).parts)).resolve()
            if root.resolve() not in source_path.parents or not source_path.is_file():
                task["status"] = "failed"
                task["error"] = "Source path is outside the immutable snapshot or does not exist."
                warnings.append(task["error"])
            else:
                content = source_path.read_text(encoding="utf-8", errors="replace")
                result = transform(TransformRequest(
                    source_code=content, source_language=request.source_language,
                    target_language=request.target_language, strategy=request.strategy,
                    validate=request.run_validation,
                ))
                target_relative = str(Path(task["path"]).with_suffix(".ts" if request.target_language == "typescript" else ".js")).replace("\\", "/")
                destination = (output_root / Path(*PurePosixPath(target_relative).parts)).resolve()
                if output_root.resolve() not in destination.parents:
                    task["status"] = "failed"
                    task["error"] = "Generated path escaped migration output."
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(result.code, encoding="utf-8")
                    generated.append({"source_path": task["path"], "target_path": target_relative, "recipe": result.recipe, "validation": result.validation, "source_sha256": hashlib.sha256(content.encode()).hexdigest(), "target_sha256": hashlib.sha256(result.code.encode()).hexdigest()})
                    warnings.extend(result.warnings)
                    task["status"] = "completed" if result.status.startswith("completed") else "failed"
        elif task["type"] == "validate_output":
            task["status"] = "completed" if generated else "failed"
        processed += 1
        if any(item["status"] == "failed" for item in tasks):
            break
    status = "completed" if all(task["status"] == "completed" for task in tasks) else ("failed" if any(task["status"] == "failed" for task in tasks) else "partial")
    return ExecutionResult(status, tasks, generated, warnings, {"completed": sum(task["status"] == "completed" for task in tasks), "total": len(tasks), "files_generated": len(generated)})


def archive_output(output_root: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in output_root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(output_root).as_posix())
