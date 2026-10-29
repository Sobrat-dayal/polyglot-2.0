import io
import zipfile

from fastapi.testclient import TestClient

import app as app_module


def test_javascript_to_typescript_is_deterministic_and_reviewable(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "transmute.db")
    app_module._init_database()
    with TestClient(app_module.app) as client:
        response = client.post("/api/v1/transmute/translate", json={
            "source_code": "const name = 'Polyglot';\nmodule.exports = name;\n",
            "source_language": "javascript", "target_language": "typescript", "mode": "type-safe",
        })
        result_id = response.json()["id"]
        diff = client.get(f"/api/v1/transmute/results/{result_id}/diff")
        approved = client.post(f"/api/v1/transmute/results/{result_id}/approve")
    assert response.status_code == 200
    assert ": string" in response.json()["generated_code"]
    assert "export default" in response.json()["generated_code"]
    assert "generated" in diff.json()["diff"]
    assert approved.json()["review_status"] == "approved"


def test_python_validation_reports_parse_errors(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "transmute-invalid.db")
    app_module._init_database()
    with TestClient(app_module.app) as client:
        response = client.post("/api/v1/transmute/translate", json={
            "source_code": "def broken(:\n  pass\n",
            "source_language": "python", "target_language": "python",
        })
    assert response.status_code == 200
    assert response.json()["validation"]["status"] == "failed"
    assert response.json()["status"] == "partially_completed"


def test_project_file_translation_enforces_snapshot_scope(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "transmute-project.db")
    app_module._init_database()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("main.js", "const value = 1;\n")
    with TestClient(app_module.app) as client:
        project = client.post("/api/v1/projects/import/zip?filename=source.zip", content=archive.getvalue()).json()
        response = client.post(f"/api/v1/projects/{project['id']}/transmute/files", json={
            "path": "main.js", "source_language": "javascript", "target_language": "typescript",
        })
        traversal = client.post(f"/api/v1/projects/{project['id']}/transmute/files", json={
            "path": "../main.js", "source_language": "javascript", "target_language": "typescript",
        })
    assert response.status_code == 200
    assert traversal.status_code == 404
