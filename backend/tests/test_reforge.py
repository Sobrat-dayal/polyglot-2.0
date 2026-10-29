import io
import zipfile

from fastapi.testclient import TestClient

import app as app_module


def _project(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "reforge.db")
    app_module._init_database()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("main.py", "print('safe')\n")
    with TestClient(app_module.app) as client:
        return client.post("/api/v1/projects/import/zip?filename=reforge.zip", content=archive.getvalue()).json()["id"]


def test_reforge_database_generation_requires_approval(tmp_path):
    project_id = _project(tmp_path)
    with TestClient(app_module.app) as client:
        response = client.post(f"/api/v1/projects/{project_id}/reforge", json={
            "project_id": project_id, "operation": "database", "mode": "generate",
            "source": "CREATE TABLE users (id INT, name VARCHAR(100));", "target": "postgresql",
        })
        operation_id = response.json()["id"]
        approved = client.post(f"/api/v1/reforge/operations/{operation_id}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_approval"
    assert "TIMESTAMPTZ" not in response.json()["result"]["sql"]
    assert approved.json()["status"] == "approved"


def test_reforge_generates_graphql_contract(tmp_path):
    project_id = _project(tmp_path)
    with TestClient(app_module.app) as client:
        response = client.post(f"/api/v1/projects/{project_id}/reforge", json={
            "project_id": project_id, "operation": "api", "mode": "generate",
            "source": "GET /users\nPOST /users", "target": "graphql", "require_approval": False,
        })
    assert response.status_code == 200
    assert "type Query" in response.json()["result"]["schema"]
    assert len(response.json()["result"]["routes"]) == 2


def test_reforge_capabilities_are_explicit():
    with TestClient(app_module.app) as client:
        response = client.get("/api/v1/reforge/capabilities")
    assert response.status_code == 200
    assert any(item["execution"] == "generate_only" for item in response.json()["items"])
