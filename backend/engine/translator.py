"""Provider-independent translation orchestration and provider adapters."""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

SUPPORTED_LANGUAGES = {
    "python", "javascript", "typescript", "java", "c", "c++", "c#",
    "go", "rust", "php", "ruby", "kotlin", "swift", "dart",
}
DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "nvidia": "qwen/qwen2.5-coder-32b-instruct",
    "groq": "qwen/qwen3-32b",
}


class TranslationError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class TranslationResult:
    code: str
    provider: str
    model: str
    explanation: str | None
    warnings: list[str]
    validation: dict[str, str]
    token_usage: dict[str, int] | None


def _prompt(
    source_code: str, source_language: str, target_language: str, mode: str,
    coding_preferences: str | None, include_explanation: bool,
) -> str:
    explanation_rule = (
        "After the code, add a section starting with EXPLANATION:." if include_explanation
        else "Return only the translated code without markdown or explanation."
    )
    return (
        "You are a senior software translator. Preserve behavior and meaningful comments. "
        f"Translate {source_language} to {target_language} in {mode} mode. "
        f"{explanation_rule}\n"
        f"Preferences: {coding_preferences or 'none'}\n"
        "Use this exact output format when explanation is requested:\n"
        "CODE:\n<code>\nEXPLANATION:\n<brief explanation>\n"
        f"SOURCE:\n{source_code}"
    )


def _split_response(text: str, include_explanation: bool) -> tuple[str, str | None]:
    clean = text.strip()
    if "```" in clean:
        clean = re.sub(r"```[a-zA-Z0-9+#.-]*\n?", "", clean).replace("```", "").strip()
    if include_explanation and "EXPLANATION:" in clean:
        code = clean.split("EXPLANATION:", 1)[0].removeprefix("CODE:").strip()
        explanation = clean.split("EXPLANATION:", 1)[1].strip()
        return code, explanation or None
    return clean.removeprefix("CODE:").strip(), None


async def _openai_compatible(
    base_url: str, api_key: str | None, model: str, prompt: str,
    temperature: float, max_tokens: int, timeout: float,
) -> tuple[str, dict[str, int] | None]:
    if not api_key:
        raise TranslationError("The selected provider is not configured on the server.", 503)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": "Bearer " + api_key},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            body = response.json()
            return body["choices"][0]["message"]["content"], body.get("usage")
    except httpx.TimeoutException as error:
        raise TranslationError("The provider request timed out.", 504) from error
    except (httpx.HTTPStatusError, KeyError, IndexError, TypeError) as error:
        raise TranslationError("The provider returned an invalid or unsuccessful response.", 502) from error


async def translate_with_provider(
    source_code: str, source_language: str, target_language: str,
    provider_name: str, model: str | None, mode: str,
    coding_preferences: str | None, include_explanation: bool,
    temperature: float, max_tokens: int,
    cancelled: Callable[[], Awaitable[bool]],
) -> TranslationResult:
    if source_language == target_language:
        raise TranslationError("Source and target languages must be different.", 422)
    selected_model = model or DEFAULT_MODELS[provider_name]
    if await cancelled():
        raise asyncio.CancelledError
    prompt = _prompt(source_code, source_language, target_language, mode, coding_preferences, include_explanation)
    timeout = float(os.getenv("POLYGLOT_PROVIDER_TIMEOUT", "60"))
    if provider_name == "nvidia":
        text, usage = await _openai_compatible(
            "https://integrate.api.nvidia.com/v1", os.getenv("NVIDIA_API_KEY"),
            selected_model, prompt, temperature, max_tokens, timeout,
        )
    elif provider_name == "groq":
        text, usage = await _openai_compatible(
            "https://api.groq.com/openai/v1", os.getenv("GROQ_API_KEY"),
            selected_model, prompt, temperature, max_tokens, timeout,
        )
    elif provider_name == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise TranslationError("The selected provider is not configured on the server.", 503)
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = await asyncio.to_thread(
                client.models.generate_content, model=selected_model, contents=prompt
            )
            text, usage = response.text, None
        except Exception as error:
            raise TranslationError("Gemini failed to generate a translation.", 502) from error
    else:
        raise TranslationError("Unsupported provider.", 422)
    code, explanation = _split_response(text, include_explanation)
    if not code:
        raise TranslationError("The provider returned empty translated code.", 502)
    return TranslationResult(
        code=code, provider=provider_name, model=selected_model,
        explanation=explanation, warnings=[],
        validation={"status": "not_run", "detail": "Language-specific validation is not configured."},
        token_usage=usage,
    )
