import asyncio
import pytest

from neural_core import AIError, AIRequest, ModelInfo, ModelRouter, OpenAICompatibleAdapter, ProviderAdapter, validate_custom_endpoint


class FakeProvider(ProviderAdapter):
    def __init__(self, name, local=False):
        self.name = name
        self.local = local

    async def models(self):
        return [ModelInfo(self.name, "test-model", frozenset({"text", "code"}), 8192, self.local, "available")]

    async def generate(self, model, messages, token_budget, timeout):
        return "generated", {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}


def test_router_respects_local_only():
    router = ModelRouter({"cloud": FakeProvider("cloud"), "local": FakeProvider("local", True)})
    adapter, model, decision = asyncio.run(router.select(
        AIRequest(messages=[{"role": "user", "content": "hi"}], privacy_mode="local_only", strategy="local_only")
    ))
    assert adapter.name == "local"
    assert model.local is True
    assert decision["strategy"] == "local_only"


def test_router_rejects_missing_capability():
    router = ModelRouter({"cloud": FakeProvider("cloud")})
    with pytest.raises(AIError):
        asyncio.run(router.select(
            AIRequest(messages=[{"role": "user", "content": "hi"}], required_capabilities={"tools"})
        ))


def test_custom_endpoint_policy():
    assert validate_custom_endpoint("https://example.com/v1") == "https://example.com/v1"
    with pytest.raises(ValueError):
        validate_custom_endpoint("http://127.0.0.1:11434/v1")


def test_openai_compatible_model_discovery_handles_null_data(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": None}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("neural_core.httpx.AsyncClient", lambda **_kwargs: Client())
    adapter = OpenAICompatibleAdapter("test", "https://example.test", {"default": "token"})
    assert asyncio.run(adapter.models()) == []
    assert validate_custom_endpoint("http://127.0.0.1:11434/v1", allow_private=True)
