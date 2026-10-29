import io
import zipfile

from fastapi.testclient import TestClient

import app as app_module


def _migration_fixture(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "metamorphosis.db")
    app_module._init_database()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("main.js", "const value = 1;\nmodule.exports = value;\n")
    with TestClient(app_module.app) as client:
        project = client.post("/api/v1/projects/import/zip?filename=source.zip", content=archive.getvalue()).json()
        analysis = client.post(f"/api/v1/projects/{project['id']}/analysis").json()
        configuration = client.post(f"/api/v1/projects/{project['id']}/stackforge/configurations", json={
            "name": "target", "source_analysis_id": analysis["analysis_id"],
            "services": [{"id": "web", "name": "Web", "language": "typescript", "framework": "nestjs"}],
        }).json()
    return project["id"], configuration["id"]


def test_metamorphosis_executes_checkpointed_file_migration(tmp_path):
    project_id, configuration_id = _migration_fixture(tmp_path)
    with TestClient(app_module.app) as client:
        created = client.post(f"/api/v1/projects/{project_id}/metamorphosis", json={
            "project_id": project_id, "configuration_id": configuration_id,
            "mode": "selected", "selected_paths": ["main.js"],
            "source_language": "javascript", "target_language": "typescript",
        })
        migration_id = created.json()["id"]
        executed = client.post(f"/api/v1/metamorphosis/{migration_id}/execute")
        status = client.get(f"/api/v1/metamorphosis/{migration_id}")
        events = client.get(f"/api/v1/metamorphosis/{migration_id}/events")
        exported = client.get(f"/api/v1/metamorphosis/{migration_id}/export")
    assert created.status_code == 200
    assert executed.status_code == 200
    assert executed.json()["status"] == "completed"
    assert executed.json()["generated"][0]["target_path"] == "main.ts"
    assert status.json()["tasks"][-1]["status"] == "completed"
    assert events.json()[-1]["event_type"] == "completed"
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")


def test_metamorphosis_cancellation_is_persisted(tmp_path):
    project_id, configuration_id = _migration_fixture(tmp_path)
    with TestClient(app_module.app) as client:
        created = client.post(f"/api/v1/projects/{project_id}/metamorphosis", json={
            "project_id": project_id, "configuration_id": configuration_id,
            "selected_paths": ["main.js"],
        })
        migration_id = created.json()["id"]
        cancelled = client.post(f"/api/v1/metamorphosis/{migration_id}/cancel")
        execute = client.post(f"/api/v1/metamorphosis/{migration_id}/execute")
    assert cancelled.json()["status"] == "cancelled"
    assert execute.status_code == 409
