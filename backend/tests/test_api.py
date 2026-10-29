import os

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
