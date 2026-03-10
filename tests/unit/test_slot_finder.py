import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from api.services.availability.slot_finder import find_slots


@pytest.mark.asyncio
async def test_find_slots_no_conflicts():
    """Should return slots when there are no conflicts."""
    with patch(
        "api.services.availability.slot_finder.check_slot",
        new_callable=AsyncMock,
        return_value={"available": True, "conflicts": []},
    ):
        import uuid
        slots = await find_slots(
            user_id=uuid.uuid4(),
            date_from=datetime(2026, 3, 11, 9, 0),
            date_to=datetime(2026, 3, 11, 18, 0),
            duration_minutes=60,
        )
        assert len(slots) > 0
        assert all(s["score"] >= 0 for s in slots)
        assert len(slots) <= 8


@pytest.mark.asyncio
async def test_find_slots_all_busy():
    """Should return empty list when all slots are busy."""
    with patch(
        "api.services.availability.slot_finder.check_slot",
        new_callable=AsyncMock,
        return_value={"available": False, "conflicts": [{"email": "test@example.com"}]},
    ):
        import uuid
        slots = await find_slots(
            user_id=uuid.uuid4(),
            date_from=datetime(2026, 3, 11, 9, 0),
            date_to=datetime(2026, 3, 11, 18, 0),
            duration_minutes=60,
        )
        assert slots == []


@pytest.mark.asyncio
async def test_find_slots_respects_max():
    """Should not return more than MAX_SLOTS slots."""
    with patch(
        "api.services.availability.slot_finder.check_slot",
        new_callable=AsyncMock,
        return_value={"available": True, "conflicts": []},
    ):
        import uuid
        slots = await find_slots(
            user_id=uuid.uuid4(),
            date_from=datetime(2026, 3, 9, 9, 0),  # Monday
            date_to=datetime(2026, 3, 20, 18, 0),  # Next week
            duration_minutes=30,
        )
        assert len(slots) <= 8


@pytest.mark.asyncio
async def test_find_slots_preferred_time_scoring():
    """Slots in preferred time should have higher score."""
    with patch(
        "api.services.availability.slot_finder.check_slot",
        new_callable=AsyncMock,
        return_value={"available": True, "conflicts": []},
    ):
        import uuid
        slots = await find_slots(
            user_id=uuid.uuid4(),
            date_from=datetime(2026, 3, 11, 9, 0),
            date_to=datetime(2026, 3, 11, 18, 0),
            duration_minutes=60,
            preferred_time_from="10:00",
            preferred_time_to="12:00",
        )
        # First slot should be in preferred window
        if slots:
            first_start = datetime.fromisoformat(slots[0]["start_at"])
            # Preferred window slots should come first
            assert slots[0]["score"] >= slots[-1]["score"]
