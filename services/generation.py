"""
Generation service — loads brain context from Supabase and calls Claude.
Supports streaming (SSE) for real-time frontend output.
"""
import asyncio
import json
import logging
from typing import AsyncIterator

import anthropic
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import UniversalBrain, FormatBrain, CopywritingPrinciple
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

CLAUDE_PRICING = {
    "claude-sonnet-4-6": {"input_per_mtok": 3.00, "output_per_mtok": 15.00},
    "claude-haiku-4-5-20251001": {"input_per_mtok": 0.80, "output_per_mtok": 4.00},
    "claude-opus-4-6": {"input_per_mtok": 15.00, "output_per_mtok": 75.00},
}


async def _log_claude_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    session_id: str | None = None,
    session_label: str | None = None,
) -> None:
    """Fire-and-forget — scheduled as asyncio.create_task(). Never raises."""
    try:
        from sqlalchemy import text
        pricing = CLAUDE_PRICING.get(model, {"input_per_mtok": 3.00, "output_per_mtok": 15.00})
        cost_usd = (
            (input_tokens / 1_000_000) * pricing["input_per_mtok"]
            + (output_tokens / 1_000_000) * pricing["output_per_mtok"]
        )
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO api_cost_log
                    (api_name, model, input_tokens, output_tokens, cost_usd, session_id, session_label)
                VALUES
                    (:api_name, :model, :input_tokens, :output_tokens, :cost_usd, :session_id, :session_label)
            """), {
                "api_name": "claude", "model": model,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "cost_usd": float(cost_usd), "session_id": session_id,
                "session_label": session_label,
            })
            await db.commit()
    except Exception as e:
        logger.warning("[cost_log] Failed to log Claude cost: %s", e)

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def _load_brain_context(
    db: AsyncSession,
    user_id: str,
    format_key: str,
) -> tuple[str, str, list[str], list[dict]]:
    """
    Returns (universal_content, format_content, principles, example_outputs).
    Raises ValueError if brain is missing or too thin.
    """
    # Universal brain
    ub_row = await db.scalar(
        select(UniversalBrain).where(UniversalBrain.user_id == user_id)
    )
    universal_content = ub_row.brain_content if ub_row else ""

    # Format brain
    fb_row = await db.scalar(
        select(FormatBrain).where(
            and_(
                FormatBrain.user_id == user_id,
                FormatBrain.format_key == format_key,
                FormatBrain.is_active == True,
                FormatBrain.deleted_at == None,
            )
        )
    )
    if not fb_row:
        raise ValueError(f"No active format brain found for format_key='{format_key}'")

    format_content = fb_row.brain_content or ""
    example_outputs = fb_row.example_outputs or []

    # All principles: universal + format-specific
    principles_rows = await db.scalars(
        select(CopywritingPrinciple).where(
            and_(
                CopywritingPrinciple.user_id == user_id,
                CopywritingPrinciple.is_active == True,
                CopywritingPrinciple.deleted_at == None,
            )
        ).order_by(CopywritingPrinciple.display_order)
    )
    principles = [r.principle_text for r in principles_rows.all()]

    if len(principles) < settings.BRAIN_MINIMUM_PRINCIPLES:
        raise ValueError(
            f"Brain has only {len(principles)} principles (minimum {settings.BRAIN_MINIMUM_PRINCIPLES}). "
            "Seed the brain before generating."
        )

    return universal_content, format_content, principles, example_outputs


def _build_system_prompt(
    universal_content: str,
    format_content: str,
    principles: list[str],
    example_outputs: list[dict],
) -> str:
    principles_block = "\n".join(f"- {p}" for p in principles)

    examples_block = ""
    if example_outputs:
        examples = []
        for ex in example_outputs[:3]:  # max 3 few-shot examples to keep context lean
            examples.append(
                f"### {ex.get('label', 'Example')}\n"
                f"**TITLE:** {ex.get('title', '')}\n\n"
                f"**DESCRIPTION:**\n{ex.get('description', '')}"
            )
        examples_block = "\n\n---\n\n".join(examples)

    return f"""You are a direct-response copywriter for Quantum Scaling (QS), a B2B growth agency that helps coaches, consultants, and service businesses scale with AI-powered webinar acquisition systems.

You generate calendar blocker copy (LinkedIn calendar invites): a title and description that get professionals to click YES or MAYBE to attend a webinar.

## Business Context
{universal_content}

## Format Rules
{format_content}

## Copywriting Principles
{principles_block}

## Real Examples (study these — match this voice and structure exactly)
{examples_block}

## Output Format
Respond with valid JSON only. No markdown, no explanation, no preamble.

{{
  "variants": [
    {{
      "variant": "A",
      "style": "Curiosity-first (Revealed: style)",
      "title": "...",
      "description": "..."
    }},
    {{
      "variant": "B",
      "style": "Outcome-first (Hormozi style)",
      "title": "...",
      "description": "..."
    }},
    {{
      "variant": "C",
      "style": "Mechanism-first (Kennedy style)",
      "title": "...",
      "description": "..."
    }}
  ]
}}

Rules:
- Generate exactly 3 variants (A, B, C) as specified above
- All client proof numbers must be verbatim from the provided brief — never fabricate
- Each description must follow the 9-part structure from the format rules
- Titles must pass the gut check: target segment reads it and thinks "oh shit, that's for me"
"""


def _build_user_prompt(
    segment: str,
    sub_niche: str | None,
    topic: str | None,
    client_story: str | None,
) -> str:
    parts = [f"Generate a calendar blocker for this target segment: **{segment}**"]

    if sub_niche:
        parts.append(f"Sub-niche: {sub_niche}")

    if topic:
        parts.append(f"Webinar topic: {topic}")
    else:
        parts.append("Webinar topic: AI-powered webinar growth system (default)")

    if client_story:
        parts.append(
            f"\nClient proof story to use (verbatim numbers only):\n{client_story}"
        )
    else:
        parts.append(
            "\nNo specific client story provided — select the best matching case study "
            "from the examples, or use segment-agnostic framing if no match exists."
        )

    return "\n".join(parts)


async def generate_calendar_blocker(
    db: AsyncSession,
    user_id: str,
    segment: str,
    sub_niche: str | None = None,
    topic: str | None = None,
    client_story: str | None = None,
) -> dict:
    """Non-streaming generation. Returns parsed JSON with 3 variants."""
    universal, format_rules, principles, examples = await _load_brain_context(
        db, user_id, "calendar_event"
    )

    system = _build_system_prompt(universal, format_rules, principles, examples)
    user_msg = _build_user_prompt(segment, sub_niche, topic, client_story)

    logger.info(
        "Generating calendar blocker — segment=%s sub_niche=%s", segment, sub_niche
    )

    message = await _client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )

    asyncio.create_task(_log_claude_cost(
        model=settings.CLAUDE_MODEL,
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
        session_id=f"{user_id}:{segment}",
        session_label=f"Calendar blocker — {segment}",
    ))

    raw = message.content[0].text.strip()

    # Strip markdown code fences if model wraps in ```json
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON parse failed: %s\nRaw: %s", e, raw[:500])
        raise ValueError(f"Model returned invalid JSON: {e}") from e

    return result


async def stream_calendar_blocker(
    db: AsyncSession,
    user_id: str,
    segment: str,
    sub_niche: str | None = None,
    topic: str | None = None,
    client_story: str | None = None,
) -> AsyncIterator[str]:
    """
    Streaming SSE generator. Yields text chunks as they arrive from Claude.
    Final chunk is a JSON object with the full parsed result.
    """
    universal, format_rules, principles, examples = await _load_brain_context(
        db, user_id, "calendar_event"
    )

    system = _build_system_prompt(universal, format_rules, principles, examples)
    user_msg = _build_user_prompt(segment, sub_niche, topic, client_story)

    full_text = []

    async with _client.messages.stream(
        model=settings.CLAUDE_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        async for chunk in stream.text_stream:
            full_text.append(chunk)
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        _final_msg = await stream.get_final_message()

    asyncio.create_task(_log_claude_cost(
        model=settings.CLAUDE_MODEL,
        input_tokens=_final_msg.usage.input_tokens,
        output_tokens=_final_msg.usage.output_tokens,
        session_id=f"{user_id}:{segment}",
        session_label=f"Calendar blocker (stream) — {segment}",
    ))

    # Parse and emit final result
    raw = "".join(full_text).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(raw)
        yield f"data: {json.dumps({'type': 'done', 'result': result})}\n\n"
    except json.JSONDecodeError as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
