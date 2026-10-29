import io
import zipfile

from fastapi.testclient import TestClient

import app as app_module


def _project(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "stackforge.db")
    app_module._init_database()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    with TestClient(app_module.app) as client:
        return client.post("/api/v1/projects/import/zip?filename=stack.zip", content=archive.getvalue()).json()["id"]


def test_stackforge_rejects_framework_language_mismatch(tmp_path):
    project_id = _project(tmp_path)
    with TestClient(app_module.app) as client:
        response = client.post(f"/api/v1/projects/{project_id}/stackforge/validate", json={
            "name": "invalid", "services": [{"id": "api", "name": "API", "language": "python", "framework": "nestjs"}],
        })
    assert response.status_code == 200
    assert response.json()["state"] == "incompatible"
    assert any("requires" in issue["explanation"] for issue in response.json()["issues"])


def test_stackforge_configuration_requires_analysis(tmp_path):
    project_id = _project(tmp_path)
    with TestClient(app_module.app) as client:
        response = client.post(f"/api/v1/projects/{project_id}/stackforge/configurations", json={
            "name": "target", "services": [{"id": "api", "name": "API", "language": "python", "framework": "fastapi"}],
        })
    assert response.status_code == 409


def test_stackforge_catalog_and_recipe_registry():
    with TestClient(app_module.app) as client:
        catalog = client.get("/api/v1/stackforge/catalog?category=database")
        recipes = client.get("/api/v1/stackforge/recipes?source=javascript&target=typescript")
    assert catalog.status_code == 200
    assert any(item["id"] == "postgresql" for item in catalog.json()["items"])
    assert recipes.json()["items"][0]["status"] == "experimental"


def test_stackforge_configuration_plan_export_and_approval(tmp_path):
    project_id = _project(tmp_path)
    with TestClient(app_module.app) as client:
        analysis = client.post(f"/api/v1/projects/{project_id}/analysis").json()
        target = {
            "name": "target", "source_analysis_id": analysis["analysis_id"],
            "services": [{"id": "api", "name": "API", "language": "python", "framework": "fastapi", "api_protocol": "rest"}],
            "databases": [{"id": "primary", "engine": "postgresql", "orm": "sqlalchemy"}],
            "authentication": {"strategy": "oidc"},
        }
        configuration = client.post(f"/api/v1/projects/{project_id}/stackforge/configurations", json=target).json()
        plan = client.post(f"/api/v1/stackforge/configurations/{configuration['id']}/plan").json()
        exported = client.get(f"/api/v1/stackforge/configurations/{configuration['id']}/export").json()
        decision = client.post(f"/api/v1/stackforge/plans/{plan['id']}/decisions", json={"status": "approved", "category": "authentication", "proposal": "Use OIDC"})
        imported = client.post(f"/api/v1/stackforge/config/import?project_id={project_id}", json={"content": exported["content"]})
    assert plan["execution_readiness"] == "blocked"
    assert exported["format"] == "polyglot.yaml"
    assert decision.status_code == 200
    assert imported.status_code == 200
