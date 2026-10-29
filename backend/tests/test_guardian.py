import io
import zipfile

from fastapi.testclient import TestClient

import app as app_module


def _project(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "guardian.db")
    app_module._init_database()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("main.py", "def add(a, b):\n    return a + b\n")
        bundle.writestr("test_main.py", "def test_add():\n    assert True\n")
    with TestClient(app_module.app) as client:
        return client.post("/api/v1/projects/import/zip?filename=guardian.zip", content=archive.getvalue()).json()["id"]


def test_guardian_is_explicit_about_dynamic_execution(tmp_path):
    project_id = _project(tmp_path)
    with TestClient(app_module.app) as client:
        response = client.post(f"/api/v1/projects/{project_id}/guardian", json={
            "project_id": project_id, "mode": "comprehensive",
            "scenarios": [{"name": "addition", "source": {"value": 3}, "target": {"value": 4}}],
        })
        verification_id = response.json()["id"]
        detail = client.get(f"/api/v1/guardian/verifications/{verification_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert any(check["status"] == "not_performed" for check in response.json()["report"]["checks"])
    assert detail.json()["evidence"]


def test_guardian_static_validation_and_test_discovery(tmp_path):
    project_id = _project(tmp_path)
    with TestClient(app_module.app) as client:
        response = client.post(f"/api/v1/projects/{project_id}/guardian", json={
            "project_id": project_id, "mode": "code",
        })
        capabilities = client.get("/api/v1/guardian/capabilities")
    assert response.status_code == 200
    assert response.json()["report"]["tests"][0]["framework"] == "pytest"
    assert capabilities.json()["items"][4]["status"] == "unavailable"


def test_guardian_static_validate_rejects_bad_python():
    with TestClient(app_module.app) as client:
        response = client.post("/api/v1/guardian/static-validate", json={"language": "python", "source": "def broken("})
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
