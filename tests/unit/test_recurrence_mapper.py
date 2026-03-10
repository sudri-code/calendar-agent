import pytest
from datetime import date

from api.services.events.recurrence_mapper import (
    graph_recurrence_to_rrule,
    rrule_to_graph_recurrence,
)


class TestGraphToRRule:
    def test_daily_no_end(self):
        recurrence = {
            "pattern": {"type": "daily", "interval": 1},
            "range": {"type": "noEnd", "startDate": "2026-03-10"},
        }
        result = graph_recurrence_to_rrule(recurrence)
        assert "FREQ=DAILY" in result
        assert "INTERVAL=1" in result
        assert "UNTIL" not in result
        assert "COUNT" not in result

    def test_daily_with_interval(self):
        recurrence = {
            "pattern": {"type": "daily", "interval": 3},
            "range": {"type": "noEnd", "startDate": "2026-03-10"},
        }
        result = graph_recurrence_to_rrule(recurrence)
        assert "FREQ=DAILY" in result
        assert "INTERVAL=3" in result

    def test_weekly_with_days(self):
        recurrence = {
            "pattern": {
                "type": "weekly",
                "interval": 1,
                "daysOfWeek": ["monday", "wednesday", "friday"],
            },
            "range": {"type": "noEnd", "startDate": "2026-03-10"},
        }
        result = graph_recurrence_to_rrule(recurrence)
        assert "FREQ=WEEKLY" in result
        assert "MO" in result
        assert "WE" in result
        assert "FR" in result

    def test_weekly_with_end_date(self):
        recurrence = {
            "pattern": {"type": "weekly", "interval": 1, "daysOfWeek": ["monday"]},
            "range": {"type": "endDate", "startDate": "2026-03-10", "endDate": "2026-06-30"},
        }
        result = graph_recurrence_to_rrule(recurrence)
        assert "UNTIL=20260630" in result

    def test_weekly_with_count(self):
        recurrence = {
            "pattern": {"type": "weekly", "interval": 2, "daysOfWeek": ["monday"]},
            "range": {"type": "numbered", "startDate": "2026-03-10", "numberOfOccurrences": 10},
        }
        result = graph_recurrence_to_rrule(recurrence)
        assert "COUNT=10" in result
        assert "INTERVAL=2" in result

    def test_absolute_monthly(self):
        recurrence = {
            "pattern": {"type": "absoluteMonthly", "interval": 1, "dayOfMonth": 15},
            "range": {"type": "noEnd", "startDate": "2026-03-10"},
        }
        result = graph_recurrence_to_rrule(recurrence)
        assert "FREQ=MONTHLY" in result
        assert "BYMONTHDAY=15" in result

    def test_relative_monthly(self):
        recurrence = {
            "pattern": {
                "type": "relativeMonthly",
                "interval": 1,
                "daysOfWeek": ["monday"],
                "index": "second",
            },
            "range": {"type": "noEnd", "startDate": "2026-03-10"},
        }
        result = graph_recurrence_to_rrule(recurrence)
        assert "FREQ=MONTHLY" in result
        assert "BYDAY=+2MO" in result

    def test_absolute_yearly(self):
        recurrence = {
            "pattern": {"type": "absoluteYearly", "interval": 1, "dayOfMonth": 10, "month": 3},
            "range": {"type": "noEnd", "startDate": "2026-03-10"},
        }
        result = graph_recurrence_to_rrule(recurrence)
        assert "FREQ=YEARLY" in result
        assert "BYMONTH=3" in result
        assert "BYMONTHDAY=10" in result


class TestRRuleToGraph:
    def test_daily(self):
        result = rrule_to_graph_recurrence("RRULE:FREQ=DAILY;INTERVAL=1", date(2026, 3, 10))
        assert result["pattern"]["type"] == "daily"
        assert result["pattern"]["interval"] == 1

    def test_weekly_with_byday(self):
        result = rrule_to_graph_recurrence("RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR", date(2026, 3, 10))
        assert result["pattern"]["type"] == "weekly"
        assert "monday" in result["pattern"]["daysOfWeek"]
        assert "wednesday" in result["pattern"]["daysOfWeek"]
        assert "friday" in result["pattern"]["daysOfWeek"]

    def test_monthly_by_day(self):
        result = rrule_to_graph_recurrence("RRULE:FREQ=MONTHLY;BYMONTHDAY=15", date(2026, 3, 10))
        assert result["pattern"]["type"] == "absoluteMonthly"
        assert result["pattern"]["dayOfMonth"] == 15

    def test_with_count(self):
        result = rrule_to_graph_recurrence("RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=10", date(2026, 3, 10))
        assert result["range"]["type"] == "numbered"
        assert result["range"]["numberOfOccurrences"] == 10

    def test_with_until(self):
        result = rrule_to_graph_recurrence(
            "RRULE:FREQ=DAILY;UNTIL=20260630T235959Z", date(2026, 3, 10)
        )
        assert result["range"]["type"] == "endDate"
        assert result["range"]["endDate"] == "2026-06-30"

    def test_roundtrip_weekly(self):
        """Test that Graph -> RRULE -> Graph preserves semantics."""
        original = {
            "pattern": {"type": "weekly", "interval": 1, "daysOfWeek": ["monday", "friday"]},
            "range": {"type": "noEnd", "startDate": "2026-03-10"},
        }
        rrule = graph_recurrence_to_rrule(original)
        back = rrule_to_graph_recurrence(rrule, date(2026, 3, 10))
        assert back["pattern"]["type"] == "weekly"
        assert "monday" in back["pattern"]["daysOfWeek"]
        assert "friday" in back["pattern"]["daysOfWeek"]
