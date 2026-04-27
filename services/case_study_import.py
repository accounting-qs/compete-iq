"""
Case-study URL importer.

Fetches a public web page, strips it to readable text, and asks OpenAI
(gpt-4o-mini) to extract title / client_name / industry / tags / content
that the copy generator can use as a case-study brain item.
"""
from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ConnectorCredential
from integrations import openai_client as oai

logger = logging.getLogger(__name__)


# Skip these tags entirely (their text is noise for extraction).
# NOTE: only tags with proper closing tags belong here — void elements like
# <meta>/<link> have no </meta>/</link> and would leave skip_depth permanently
# elevated, swallowing the rest of the document.
_SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}
_BLOCK_TAGS = {
    "p", "div", "section", "article", "header", "footer", "main", "nav",
    "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br", "hr",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        # Collapse whitespace inside lines but preserve paragraph breaks.
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        out: list[str] = []
        blank = False
        for ln in lines:
            if not ln:
                if not blank and out:
                    out.append("")
                blank = True
            else:
                out.append(ln)
                blank = False
        return "\n".join(out).strip()


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception as exc:
        logger.warning("HTML parse error, falling back to regex strip: %s", exc)
        return re.sub(r"<[^>]+>", " ", html)
    return parser.text()


async def _fetch_url(url: str) -> str:
    headers = {
        # Some marketing pages 403 unfamiliar UAs; pretend to be a normal browser.
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code != 200:
        raise CaseStudyImportError(f"Page returned HTTP {resp.status_code}")
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype.lower() and "<html" not in resp.text[:500].lower():
        raise CaseStudyImportError(f"URL did not return HTML (content-type: {ctype})")
    return resp.text


async def _get_openai_key(db: AsyncSession) -> str:
    row = (await db.execute(
        select(ConnectorCredential).where(ConnectorCredential.provider == "openai")
    )).scalar_one_or_none()
    if not row:
        raise CaseStudyImportError(
            "OpenAI API key not configured. Add it on the Connectors page."
        )
    return row.api_key


_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "client_name", "industry", "tags", "content"],
    "properties": {
        "title": {
            "type": "string",
            "description": "Short headline for this case study, e.g. 'Jason Rotman — 3x revenue with webinars'.",
        },
        "client_name": {
            "type": "string",
            "description": "Person + company if available, e.g. 'Jason Rotman, Elevate Financial Partners'. Empty string if unknown.",
        },
        "industry": {
            "type": "string",
            "description": "Concise industry label (e.g. 'Financial Advisory', 'Coaching & Training', 'SaaS', 'Agency'). Empty string if unclear.",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-6 lowercase tags useful for matching (e.g. 'webinar', 'b2b', 'high-ticket', 'solo-founder').",
        },
        "content": {
            "type": "string",
            "description": (
                "Self-contained case-study summary suitable for use as RAG context in copy generation. "
                "Include: who the client is, the problem, what they did, and quantified outcomes / metrics / "
                "testimonials when present. 150-400 words. Plain text, no markdown headers."
            ),
        },
    },
}


_SYSTEM_PROMPT = (
    "You extract structured case-study data from a marketing/case-study web page. "
    "Be faithful to the source — do not invent metrics or quotes. "
    "If a field is genuinely absent, use an empty string (or empty array for tags) rather than guessing."
)


class CaseStudyImportError(Exception):
    pass


async def import_case_study_from_url(
    db: AsyncSession,
    url: str,
    notes: str | None = None,
    max_text_chars: int = 18000,
) -> dict[str, Any]:
    """
    Returns a dict shaped like the CaseStudyCreate payload:
    {title, client_name, industry, tags, content, source_url}.

    Raises CaseStudyImportError on any user-facing failure.
    """
    api_key = await _get_openai_key(db)

    try:
        html = await _fetch_url(url)
    except httpx.HTTPError as exc:
        raise CaseStudyImportError(f"Could not fetch URL: {exc}")

    text = _html_to_text(html)
    if len(text) < 80:
        raise CaseStudyImportError(
            "Page had almost no readable text — likely JS-rendered or blocked."
        )
    text = text[:max_text_chars]

    user_prompt_parts = [f"Source URL: {url}", ""]
    if notes:
        user_prompt_parts += [f"Hints from the user about this case study: {notes.strip()}", ""]
    user_prompt_parts += ["Page content:", text]
    user_prompt = "\n".join(user_prompt_parts)

    try:
        extracted = await oai.chat_json(
            api_key=api_key,
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            schema=_EXTRACTION_SCHEMA,
        )
    except oai.OpenAIError as exc:
        raise CaseStudyImportError(f"OpenAI extraction failed: {exc}")

    title = (extracted.get("title") or "").strip()
    content = (extracted.get("content") or "").strip()
    if not title or not content:
        raise CaseStudyImportError("Extraction returned empty title or content.")

    tags_raw = extracted.get("tags") or []
    tags = [str(t).strip().lower() for t in tags_raw if str(t).strip()]

    return {
        "title": title,
        "client_name": (extracted.get("client_name") or "").strip() or None,
        "industry": (extracted.get("industry") or "").strip() or None,
        "tags": tags,
        "content": content,
        "source_url": url,
    }
