import json
import uuid
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.db.session import async_session_factory
from api.exceptions import LLMParsingError
from api.models.llm_session import LlmSession
from api.services.llm.openrouter_client import OpenRouterClient
from shared.schemas.event import AttendeeInfo, EventDraft, RecurrenceConfig

logger = structlog.get_logger()

PROMPT_PATH = Path(__file__).parent / "prompts" / "event_parser.txt"
SESSION_TTL_MINUTES = 30
MAX_CONTEXT_TURNS = 4


def _load_system_prompt(today: date) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{today}", today.isoformat())


async def _get_or_create_session(
    user_id: uuid.UUID,
    task_type: str = "create_event",
) -> tuple[LlmSession, bool]:
    """Get existing LLM session or create a new one."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(LlmSession).where(
                LlmSession.user_id == user_id,
                LlmSession.task_type == task_type,
                LlmSession.expires_at > datetime.now(timezone.utc),
            )
        )
        llm_session = result.scalar_one_or_none()

        is_new = llm_session is None
        if is_new:
            llm_session = LlmSession(
                user_id=user_id,
                task_type=task_type,
                context_json={"turns": []},
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=SESSION_TTL_MINUTES),
            )
            session.add(llm_session)
            await session.commit()
            await session.refresh(llm_session)

        return llm_session, is_new


async def _save_turn(session_id: uuid.UUID, role: str, content: str) -> None:
    """Append a conversation turn to the LLM session."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(LlmSession).where(LlmSession.id == session_id)
        )
        llm_session = result.scalar_one_or_none()
        if not llm_session:
            return

        turns: list = llm_session.context_json.get("turns", [])
        turns.append({"role": role, "content": content})
        # Keep only last MAX_CONTEXT_TURNS * 2 entries
        if len(turns) > MAX_CONTEXT_TURNS * 2:
            turns = turns[-(MAX_CONTEXT_TURNS * 2):]

        llm_session.context_json = {"turns": turns}
        llm_session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=SESSION_TTL_MINUTES)
        await session.commit()


def _parse_llm_response(raw: dict) -> Optional[EventDraft]:
    """Parse LLM JSON response into EventDraft."""
    # Parse date and time
    date_range = raw.get("date_range")
    start_time = raw.get("start_time")
    duration = raw.get("duration_minutes", 60) or 60

    if not date_range or not start_time:
        return None

    try:
        start_date = date_range.get("from") or date_range.get("to")
        start_dt_str = f"{start_date}T{start_time}:00"
        start_at = datetime.fromisoformat(start_dt_str)
        end_at = start_at + timedelta(minutes=duration)
    except (ValueError, TypeError):
        return None

    # Parse attendees
    attendees = []
    for p in raw.get("participants", []):
        if p.get("email"):
            attendees.append(AttendeeInfo(name=p.get("name"), email=p["email"]))
        elif p.get("name"):
            # Email-less attendee - will need resolution
            attendees.append(AttendeeInfo(name=p["name"], email=f"{p['name'].replace(' ', '.').lower()}@unknown"))

    # Parse recurrence
    recurrence = None
    rec_raw = raw.get("recurrence")
    if rec_raw:
        try:
            recurrence = RecurrenceConfig(
                frequency=rec_raw.get("frequency", "daily"),
                interval=rec_raw.get("interval", 1),
                days_of_week=rec_raw.get("days_of_week"),
                end_type=rec_raw.get("end_type", "no_end"),
                end_date=rec_raw.get("end_date"),
                count=rec_raw.get("count"),
            )
        except Exception:
            pass

    return EventDraft(
        title=raw.get("title") or "Встреча",
        start_at=start_at,
        end_at=end_at,
        timezone="UTC",
        description=raw.get("description"),
        attendees=attendees,
        recurrence=recurrence,
    )


async def parse_event_text(
    text: str,
    user_id: uuid.UUID,
    today: date,
) -> dict:
    """Parse free-form Russian text into event draft using LLM."""
    llm_session, is_new = await _get_or_create_session(user_id)

    system_prompt = _load_system_prompt(today)

    # Build messages with context
    async with async_session_factory() as session:
        result = await session.execute(
            select(LlmSession).where(LlmSession.id == llm_session.id)
        )
        current_session = result.scalar_one_or_none()
        prior_turns = current_session.context_json.get("turns", []) if current_session else []

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(prior_turns[-MAX_CONTEXT_TURNS * 2:])
    messages.append({"role": "user", "content": text})

    try:
        async with OpenRouterClient() as client:
            response = await client.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
            )
    except Exception as e:
        logger.error("LLM API error", error=str(e))
        raise LLMParsingError(f"LLM request failed: {e}")

    # Extract content
    choices = response.get("choices", [])
    if not choices:
        raise LLMParsingError("LLM returned no choices")

    content = choices[0].get("message", {}).get("content", "")

    # Save turn
    await _save_turn(llm_session.id, "user", text)
    await _save_turn(llm_session.id, "assistant", content)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMParsingError(f"Invalid JSON from LLM: {e}")

    # Try to build EventDraft
    draft = _parse_llm_response(parsed)

    return {
        "raw": parsed,
        "draft": draft.model_dump() if draft else None,
        "intent": parsed.get("intent", "unknown"),
        "missing_fields": parsed.get("missing_fields", []),
        "needs_confirmation": parsed.get("needs_confirmation", True),
        "session_id": str(llm_session.id),
    }
