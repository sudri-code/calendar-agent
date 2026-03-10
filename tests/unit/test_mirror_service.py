import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_build_mirror_body():
    """Test mirror event body construction."""
    from api.services.events.mirror_service import build_mirror_body

    primary = MagicMock()
    primary.title = "Team Meeting"
    primary.start_at = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    primary.end_at = datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc)
    primary.timezone = "UTC"
    primary.attendees_json = [
        {"emailAddress": {"address": "ivan@example.com"}, "name": "Ivan"},
    ]
    primary.sync_group_id = uuid.uuid4()

    body = build_mirror_body(primary, "Work Calendar")

    assert body["subject"] == "[Занято] Team Meeting"
    assert "Зеркальная блокировка" in body["body"]["content"]
    assert "Team Meeting" in body["body"]["content"]
    assert "Work Calendar" in body["body"]["content"]
    assert body["showAs"] == "busy"
    assert body["isReminderOn"] == False
    assert body["attendees"] == []


@pytest.mark.asyncio
async def test_sync_mirror_skips_missing_primary():
    """sync_mirror_to_primary should log warning and return if primary not found."""
    with patch("api.services.events.mirror_service.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_factory.return_value = mock_session

        from api.services.events.mirror_service import sync_mirror_to_primary
        # Should not raise, just return
        await sync_mirror_to_primary(uuid.uuid4())
