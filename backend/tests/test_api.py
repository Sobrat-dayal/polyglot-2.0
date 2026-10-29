import os
import io
import zipfile

os.environ["POLYGLOT_DATABASE_PATH"] = ":memory:"

from fastapi.testclient import TestClient

import app as app_module
from engine.translator import TranslationResult

app = app_module.app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_translation_rejects_empty_source():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/translate",
            json={"source_lang": "python", "target_lang": "go", "source_code": ""},
        )
    assert response.status_code == 422


def test_translation_rejects_same_language():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/translate",
            json={"source_lang": "python", "target_lang": "python", "source_code": "print(1)"},
        )
    assert response.status_code == 422


def test_translation_persists_success(monkeypatch, tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "translations.db")
    app_module._init_database()

    async def fake_translation(**kwargs):
        return TranslationResult(
            code="console.log(1)",
            provider="gemini",
            model="gemini-test",
            explanation="Converted print to console.log.",
            warnings=[],
            validation={"status": "not_run"},
            token_usage=None,
        )

    monkeypatch.setattr("app.translate_with_provider", fake_translation)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/translate",
            json={"source_lang": "python", "target_lang": "javascript", "source_code": "print(1)"},
        )
        history_response = client.get("/api/v1/history")
    assert response.status_code == 200
    assert response.json()["generated_code"] == "console.log(1)"
    assert history_response.status_code == 200
    assert history_response.json()[0]["id"] == response.json()["id"]


def test_project_and_safe_zip_import(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "projects.db")
    app_module._init_database()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("src/main.py", "print('ok')")
    with TestClient(app) as client:
        project = client.post(
            "/api/v1/projects/import/zip?filename=demo.zip",
            content=archive.getvalue(),
            headers={"content-type": "application/zip"},
        )
        files = client.get(f"/api/v1/projects/{project.json()['id']}/files")
    assert project.status_code == 200
    assert files.json()["files"][0]["relative_path"] == "src/main.py"


def test_zip_slip_is_rejected(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "unsafe.db")
    app_module._init_database()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.txt", "no")
    with TestClient(app) as client:
        response = client.post("/api/v1/projects/import/zip", content=archive.getvalue())
    assert response.status_code == 422


def test_account_project_job_and_artifact_lifecycle(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "account.db")
    app_module._init_database()
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "developer@example.com", "password": "correct horse battery"},
        )
        assert registered.status_code == 200
        project = client.post("/api/v1/projects", json={"name": "Workspace project"})
        assert project.status_code == 200
        project_id = project.json()["id"]
        job = client.post(
            "/api/v1/jobs",
            json={"project_id": project_id, "type": "index", "idempotency_key": "index-1"},
        )
        duplicate = client.post(
            "/api/v1/jobs",
            json={"project_id": project_id, "type": "index", "idempotency_key": "index-1"},
        )
        artifact = client.post(
            f"/api/v1/projects/{project_id}/artifacts",
            files={"file": ("report.txt", b"report contents", "text/plain")},
        )
    assert job.status_code == 200
    assert duplicate.json()["id"] == job.json()["id"]
    assert artifact.status_code == 200
