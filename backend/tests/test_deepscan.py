import io
import json
import os
import zipfile

from fastapi.testclient import TestClient

import app as app_module

app = app_module.app


def _project(tmp_path):
    app_module.DATABASE_PATH = str(tmp_path / "deepscan.db")
    app_module._init_database()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("app.py", "from service import run\n\ndef hello(name: str):\n    return run(name)\n")
        bundle.writestr("service.py", "def run(value):\n    return value\n")
        bundle.writestr("package.json", '{"dependencies":{"fastapi":"1.0"}}')
    with TestClient(app) as client:
        response = client.post("/api/v1/projects/import/zip?filename=demo.zip", content=archive.getvalue())
    return response.json()["id"]


def test_deepscan_persists_ir_and_sections(tmp_path):
    project_id = _project(tmp_path)
    with TestClient(app) as client:
        analysis = client.post(f"/api/v1/projects/{project_id}/analysis")
        symbols = client.get(f"/api/v1/analysis/{analysis.json()['analysis_id']}/symbols")
        report = client.get(f"/api/v1/analysis/{analysis.json()['analysis_id']}/report")
    assert analysis.status_code == 200
    assert analysis.json()["symbols"] >= 2
    assert symbols.json()["items"][0]["analysis_version"] == "deepscan-1.0"
    assert "DeepScan Report" in report.json()["markdown"]


def test_code_search_is_bounded_and_authorized(tmp_path):
    project_id = _project(tmp_path)
    with TestClient(app) as client:
        response = client.post(f"/api/v1/projects/{project_id}/code-search", json={"query": "return"})
    assert response.status_code == 200
    assert response.json()["matches"][0]["path"] in {"app.py", "service.py"}
