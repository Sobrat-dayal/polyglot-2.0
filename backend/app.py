"""Polyglot 2.0 canonical translation API.

The provider boundary is deliberately kept separate from FastAPI so providers
can be mocked in tests and additional OpenAI-compatible services can be added
without changing the HTTP contract.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.translator import (
    SUPPORTED_LANGUAGES,
    TranslationError,
    translate_with_provider,
)

DATABASE_PATH = os.getenv("POLYGLOT_DATABASE_PATH", "polyglot.db")


class TranslationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_code: str = Field(min_length=1, max_length=500_000)
    source_language: str = Field(alias="source_lang", min_length=1)
    target_language: str = Field(alias="target_lang", min_length=1)
    provider: Literal["gemini", "nvidia", "groq"] = "gemini"
    model: str | None = None
    mode: Literal[
        "standard", "idiomatic", "educational", "modernize",
        "type-safe", "performance-oriented"
    ] = "standard"
    coding_preferences: str | None = Field(default=None, max_length=5_000)
    include_explanation: bool = True
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=4_096, ge=256, le=32_768)

    @field_validator("source_language", "target_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {value}")
        return normalized


class TranslationResponse(BaseModel):
    id: str
    generated_code: str
    source_language: str
    target_language: str
    provider: str
    model: str
    status: Literal["completed"]
    explanation: str | None
    warnings: list[str]
    validation: dict[str, Any]
    duration_ms: int
    token_usage: dict[str, int] | None = None


class HistoryItem(BaseModel):
    id: str
    source_language: str
    target_language: str
    provider: str
    model: str
    status: str
    created_at: str


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _init_database() -> None:
    with _connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS translations (
                id TEXT PRIMARY KEY,
                source_code TEXT NOT NULL,
                generated_code TEXT NOT NULL,
                source_language TEXT NOT NULL,
                target_language TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                explanation TEXT,
                warnings TEXT NOT NULL,
                validation TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    _init_database()
    yield


app = FastAPI(title="Polyglot 2.0 API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("POLYGLOT_ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "polyglot-api"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    try:
        with _connection() as connection:
            connection.execute("SELECT 1")
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Database is not ready") from error
    return {"status": "ready"}


@app.post("/api/v1/translate", response_model=TranslationResponse)
async def translate(payload: TranslationRequest, request: Request) -> TranslationResponse:
    started = time.perf_counter()
    translation_id = str(uuid.uuid4())
    try:
        result = await translate_with_provider(
            source_code=payload.source_code,
            source_language=payload.source_language,
            target_language=payload.target_language,
            provider_name=payload.provider,
            model=payload.model,
            mode=payload.mode,
            coding_preferences=payload.coding_preferences,
            include_explanation=payload.include_explanation,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            cancelled=lambda: await_request_cancelled(request),
        )
    except asyncio.CancelledError as error:
        raise HTTPException(status_code=499, detail="Translation request was cancelled") from error
    except TranslationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error

    duration_ms = int((time.perf_counter() - started) * 1000)
    created_at = datetime.now(timezone.utc).isoformat()
    with _connection() as connection:
        connection.execute(
            """INSERT INTO translations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                translation_id, payload.source_code, result.code,
                payload.source_language, payload.target_language,
                result.provider, result.model, "completed", result.explanation,
                str(result.warnings), str(result.validation), duration_ms, created_at,
            ),
        )
    return TranslationResponse(
        id=translation_id,
        generated_code=result.code,
        source_language=payload.source_language,
        target_language=payload.target_language,
        provider=result.provider,
        model=result.model,
        status="completed",
        explanation=result.explanation,
        warnings=result.warnings,
        validation=result.validation,
        duration_ms=duration_ms,
        token_usage=result.token_usage,
    )


async def await_request_cancelled(request: Request) -> bool:
    return await request.is_disconnected()


@app.get("/api/v1/history", response_model=list[HistoryItem])
async def history(limit: Annotated[int, Field(ge=1, le=100)] = 50):
    with _connection() as connection:
        rows = connection.execute(
            "SELECT id, source_language, target_language, provider, model, status, created_at "
            "FROM translations ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [HistoryItem(**dict(row)) for row in rows]


@app.delete("/api/v1/history/{translation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history(translation_id: str) -> None:
    with _connection() as connection:
        cursor = connection.execute("DELETE FROM translations WHERE id = ?", (translation_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Translation not found")


@app.post("/api/translate", response_model=TranslationResponse, include_in_schema=False)
async def legacy_translate(payload: TranslationRequest, request: Request):
    return await translate(payload, request)
