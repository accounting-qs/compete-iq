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


_METRIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["label", "before", "after"],
    "properties": {
        "label": {
            "type": "string",
            "description": "What the metric measures, e.g. 'Annual revenue', 'Sales calls per month', 'Webinar attendees per month'.",
        },
        "before": {
            "type": "string",
            "description": "Pre-state as it appears on the page (e.g. '$120K', 'Sporadic', '0'). Empty string if not stated.",
        },
        "after": {
            "type": "string",
            "description": "Post-state as it appears on the page (e.g. '$360K', '62', '400+'). Empty string if not stated.",
        },
    },
}


_PERSONA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["role", "company_size", "target_market"],
    "properties": {
        "role": {
            "type": "string",
            "description": "Client's role / archetype, e.g. 'Independent financial advisor', 'Solo founder coach'. Empty if unclear.",
        },
        "company_size": {
            "type": "string",
            "description": "Team size as stated on the page, e.g. 'Solo founder + 1 assistant', '5-10 employees'. Empty if unstated.",
        },
        "target_market": {
            "type": "string",
            "description": "Who the client serves, e.g. 'High-net-worth individuals', 'B2B SaaS founders'. Empty if unstated.",
        },
    },
}


_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "title", "client_name", "industry", "tags", "content",
        "headline", "quote", "metrics", "pain_points", "outcomes", "persona",
    ],
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
                "Self-contained narrative summary, 150-400 words, plain text, no markdown headers. "
                "Who the client is, the problem, what they did, and quantified outcomes."
            ),
        },
        "headline": {
            "type": "string",
            "description": (
                "Program / offer / product name promoted on the page (e.g. '10X GROWTH Accelerator'). "
                "This is NOT the case-study title — it's the offer being sold. Empty string if absent."
            ),
        },
        "quote": {
            "type": "string",
            "description": (
                "VERBATIM testimonial from the client. Copy the words exactly as they appear, "
                "preserving the client's voice, em-dashes, and tone. Do NOT paraphrase or smooth out. "
                "Empty string if no first-person quote exists on the page."
            ),
        },
        "metrics": {
            "type": "array",
            "items": _METRIC_SCHEMA,
            "description": (
                "Discrete before/after KPIs as separate objects. Use the exact numbers and units from the "
                "page (e.g. '$120K' → '$360K'). If only an after-value is shown (e.g. '400+ attendees/month'), "
                "leave 'before' empty. Do NOT mash multiple metrics into one entry."
            ),
        },
        "pain_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "3-5 specific pain phrases from the 'before' state, in the client's voice when possible "
                "(e.g. 'inconsistent lead flow', 'ineffective marketing strategies'). "
                "Short fragments, not full sentences. Empty array if not stated."
            ),
        },
        "outcomes": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "3-5 specific outcome phrases from the 'after' state, ideally tied to a metric or "
                "behaviour change (e.g. 'peak-performing webinar system', '60+ qualified sales calls / month'). "
                "Short fragments, not full sentences."
            ),
        },
        "persona": _PERSONA_SCHEMA,
    },
}


_SYSTEM_PROMPT = (
    "You extract structured case-study data from a marketing / case-study web page. "
    "Two strict rules:\n"
    "1. PRESERVE DIRECT QUOTES VERBATIM. Copy testimonials exactly — never paraphrase, "
    "smooth, or summarise the client's words. The quote field must be a real first-person sentence "
    "from the page, character-for-character.\n"
    "2. EXTRACT METRICS AS DISCRETE before/after PAIRS, not prose. If the page shows three KPIs, "
    "return three separate metric objects with the labels and numbers as they appear.\n"
    "If a field is genuinely absent, use an empty string (or empty array). Never invent numbers, "
    "quotes, or claims that aren't on the page."
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
    {title, client_name, industry, tags, content, source_url, structured}.

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

    structured = _normalise_structured(extracted)

    return {
        "title": title,
        "client_name": (extracted.get("client_name") or "").strip() or None,
        "industry": (extracted.get("industry") or "").strip() or None,
        "tags": tags,
        "content": content,
        "source_url": url,
        "structured": structured,
    }


def _normalise_structured(extracted: dict[str, Any]) -> dict[str, Any] | None:
    """
    Pulls the rich extraction fields out of the OpenAI response and trims them
    to a clean shape suitable for storage in case_studies.structured.
    Returns None when the model gave us nothing useful (so we don't bloat the row).
    """
    headline = (extracted.get("headline") or "").strip()
    quote = (extracted.get("quote") or "").strip()

    metrics_raw = extracted.get("metrics") or []
    metrics: list[dict[str, str]] = []
    for m in metrics_raw:
        if not isinstance(m, dict):
            continue
        label = str(m.get("label") or "").strip()
        before = str(m.get("before") or "").strip()
        after = str(m.get("after") or "").strip()
        if not label and not before and not after:
            continue
        metrics.append({"label": label, "before": before, "after": after})

    pain_points = [
        str(x).strip() for x in (extracted.get("pain_points") or [])
        if str(x or "").strip()
    ]
    outcomes = [
        str(x).strip() for x in (extracted.get("outcomes") or [])
        if str(x or "").strip()
    ]

    persona_raw = extracted.get("persona") or {}
    persona: dict[str, str] = {}
    if isinstance(persona_raw, dict):
        for key in ("role", "company_size", "target_market"):
            v = str(persona_raw.get(key) or "").strip()
            if v:
                persona[key] = v

    has_any = (
        headline or quote or metrics or pain_points or outcomes or persona
    )
    if not has_any:
        return None

    return {
        "headline": headline,
        "quote": quote,
        "metrics": metrics,
        "pain_points": pain_points,
        "outcomes": outcomes,
        "persona": persona,
    }
