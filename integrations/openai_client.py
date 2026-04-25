"""
OpenAI Chat Completions client (HTTP, no SDK).

Used by the case-study URL importer to extract structured fields from
fetched page HTML/text. Single call site today; keep narrow.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openai.com/v1"
EXTRACTION_MODEL = "gpt-4o-mini"


class OpenAIError(Exception):
    pass


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def verify_api_key(api_key: str) -> bool:
    """Cheap auth check — list models. Returns True only on 200."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{BASE_URL}/models", headers=_headers(api_key))
    if resp.status_code == 401:
        return False
    if resp.status_code != 200:
        raise OpenAIError(f"OpenAI verify failed ({resp.status_code}): {resp.text[:200]}")
    return True


async def chat_json(
    api_key: str,
    system: str,
    user: str,
    model: str = EXTRACTION_MODEL,
    schema: dict[str, Any] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1500,
) -> dict[str, Any]:
    """
    Send a chat completion and return parsed JSON.

    If `schema` is provided, uses Structured Outputs (response_format =
    json_schema, strict=True). Otherwise falls back to json_object mode.
    """
    if schema is not None:
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": "extraction",
                "strict": True,
                "schema": schema,
            },
        }
    else:
        response_format = {"type": "json_object"}

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": response_format,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{BASE_URL}/chat/completions",
            headers=_headers(api_key),
            json=payload,
        )

    if resp.status_code == 401:
        raise OpenAIError("Invalid OpenAI API key")
    if resp.status_code != 200:
        raise OpenAIError(f"OpenAI returned {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise OpenAIError(f"Unexpected OpenAI response shape: {exc}")

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise OpenAIError(f"OpenAI returned non-JSON content: {exc}")
