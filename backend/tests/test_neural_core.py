import asyncio
import pytest

from neural_core import AIError, AIRequest, ModelInfo, ModelRouter, ProviderAdapter, validate_custom_endpoint


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
    assert validate_custom_endpoint("http://127.0.0.1:11434/v1", allow_private=True)
