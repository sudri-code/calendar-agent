import pytest
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_parse_create_event():
    """Test that LLM parser returns EventDraft for create_event intent."""
    mock_response = {
        "choices": [
            {
                "message": {
                    "content": """{
                        "intent": "create_event",
                        "confidence": 0.95,
                        "title": "Встреча с Иваном",
                        "date_range": {"from": "2026-03-11", "to": "2026-03-11"},
                        "start_time": "15:00",
                        "duration_minutes": 60,
                        "participants": [{"name": "Иван", "email": null}],
                        "description": null,
                        "target_calendar_hint": null,
                        "missing_fields": [],
                        "needs_confirmation": false,
                        "recurrence": null
                    }"""
                }
            }
        ]
    }

    with patch("api.services.llm.parser._get_or_create_session") as mock_session_fn, \
         patch("api.services.llm.parser._save_turn") as mock_save, \
         patch("api.services.llm.openrouter_client.OpenRouterClient.chat_completion", new_callable=AsyncMock, return_value=mock_response), \
         patch("api.services.llm.parser.async_session_factory") as mock_factory:

        mock_session = MagicMock()
        mock_session.id = uuid.uuid4()
        mock_session_fn.return_value = (mock_session, True)

        mock_db_session = AsyncMock()
        mock_db_session.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_db_session.__aexit__ = AsyncMock(return_value=False)
        mock_db_result = MagicMock()
        mock_session_obj = MagicMock()
        mock_session_obj.context_json = {"turns": []}
        mock_db_result.scalar_one_or_none.return_value = mock_session_obj
        mock_db_session.execute = AsyncMock(return_value=mock_db_result)
        mock_factory.return_value = mock_db_session
        mock_save.return_value = None

        from api.services.llm.parser import parse_event_text
        result = await parse_event_text(
            text="Встреча с Иваном завтра в 15:00",
            user_id=uuid.uuid4(),
            today=date(2026, 3, 10),
        )

        assert result["intent"] == "create_event"
        assert result["draft"] is not None
        assert result["draft"]["title"] == "Встреча с Иваном"


@pytest.mark.asyncio
async def test_parse_recurring_event():
    """Test parsing of recurring event."""
    mock_response = {
        "choices": [
            {
                "message": {
                    "content": """{
                        "intent": "create_event",
                        "confidence": 0.9,
                        "title": "Встреча с командой",
                        "date_range": {"from": "2026-03-16", "to": "2026-03-16"},
                        "start_time": "10:00",
                        "duration_minutes": 60,
                        "participants": [],
                        "description": null,
                        "target_calendar_hint": null,
                        "missing_fields": [],
                        "needs_confirmation": false,
                        "recurrence": {
                            "frequency": "weekly",
                            "interval": 1,
                            "days_of_week": ["MO"],
                            "end_type": "no_end",
                            "end_date": null,
                            "count": null
                        }
                    }"""
                }
            }
        ]
    }

    with patch("api.services.llm.parser._get_or_create_session") as mock_session_fn, \
         patch("api.services.llm.parser._save_turn") as mock_save, \
         patch("api.services.llm.openrouter_client.OpenRouterClient.chat_completion", new_callable=AsyncMock, return_value=mock_response), \
         patch("api.services.llm.parser.async_session_factory") as mock_factory:

        mock_session = MagicMock()
        mock_session.id = uuid.uuid4()
        mock_session_fn.return_value = (mock_session, True)

        mock_db_session = AsyncMock()
        mock_db_session.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_db_session.__aexit__ = AsyncMock(return_value=False)
        mock_db_result = MagicMock()
        mock_session_obj = MagicMock()
        mock_session_obj.context_json = {"turns": []}
        mock_db_result.scalar_one_or_none.return_value = mock_session_obj
        mock_db_session.execute = AsyncMock(return_value=mock_db_result)
        mock_factory.return_value = mock_db_session
        mock_save.return_value = None

        from api.services.llm.parser import parse_event_text
        result = await parse_event_text(
            text="Встреча с командой каждый понедельник в 10:00",
            user_id=uuid.uuid4(),
            today=date(2026, 3, 10),
        )

        assert result["intent"] == "create_event"
        assert result["draft"] is not None
        assert result["draft"]["recurrence"] is not None
        assert result["draft"]["recurrence"]["frequency"] == "weekly"
