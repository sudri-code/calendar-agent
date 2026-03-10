"""
Maps between Microsoft Graph patternedRecurrence format and RRULE strings.
"""
from datetime import date
from typing import Optional


GRAPH_DAY_MAP = {
    "sunday": "SU",
    "monday": "MO",
    "tuesday": "TU",
    "wednesday": "WE",
    "thursday": "TH",
    "friday": "FR",
    "saturday": "SA",
}

RRULE_DAY_MAP = {v: k for k, v in GRAPH_DAY_MAP.items()}

WEEK_INDEX_MAP = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "last": -1,
}

WEEK_INDEX_REVERSE = {v: k for k, v in WEEK_INDEX_MAP.items()}


def _graph_days_to_rrule(days: list[str]) -> str:
    """Convert Graph day names list to RRULE BYDAY value."""
    return ",".join(GRAPH_DAY_MAP.get(d.lower(), d.upper()[:2]) for d in days)


def _rrule_days_to_graph(byday: str) -> list[str]:
    """Convert RRULE BYDAY value to Graph day names."""
    parts = byday.split(",")
    result = []
    for p in parts:
        p = p.strip()
        # Remove numeric prefix like +2MO or -1FR
        day_code = p.lstrip("+-0123456789")
        result.append(RRULE_DAY_MAP.get(day_code, day_code.lower()))
    return result


def graph_recurrence_to_rrule(recurrence: dict) -> str:
    """Convert Graph patternedRecurrence to RRULE string."""
    pattern = recurrence.get("pattern", {})
    range_ = recurrence.get("range", {})

    ptype = pattern.get("type", "").lower()
    interval = pattern.get("interval", 1)

    parts = []

    if ptype == "daily":
        parts.append(f"FREQ=DAILY;INTERVAL={interval}")

    elif ptype == "weekly":
        days = _graph_days_to_rrule(pattern.get("daysOfWeek", []))
        parts.append(f"FREQ=WEEKLY;INTERVAL={interval}")
        if days:
            parts.append(f"BYDAY={days}")

    elif ptype == "absolutemonthly":
        day_of_month = pattern.get("dayOfMonth", 1)
        parts.append(f"FREQ=MONTHLY;INTERVAL={interval};BYMONTHDAY={day_of_month}")

    elif ptype == "relativemonthly":
        days = pattern.get("daysOfWeek", [])
        index = pattern.get("index", "first")
        week_num = WEEK_INDEX_MAP.get(index.lower(), 1)
        if days:
            day_code = GRAPH_DAY_MAP.get(days[0].lower(), "MO")
            prefix = f"+{week_num}" if week_num > 0 else str(week_num)
            parts.append(f"FREQ=MONTHLY;INTERVAL={interval};BYDAY={prefix}{day_code}")
        else:
            parts.append(f"FREQ=MONTHLY;INTERVAL={interval}")

    elif ptype == "absoluteyearly":
        day_of_month = pattern.get("dayOfMonth", 1)
        month = pattern.get("month", 1)
        parts.append(f"FREQ=YEARLY;INTERVAL={interval};BYMONTH={month};BYMONTHDAY={day_of_month}")

    elif ptype == "relativeyearly":
        days = pattern.get("daysOfWeek", [])
        index = pattern.get("index", "first")
        month = pattern.get("month", 1)
        week_num = WEEK_INDEX_MAP.get(index.lower(), 1)
        if days:
            day_code = GRAPH_DAY_MAP.get(days[0].lower(), "MO")
            prefix = f"+{week_num}" if week_num > 0 else str(week_num)
            parts.append(f"FREQ=YEARLY;INTERVAL={interval};BYMONTH={month};BYDAY={prefix}{day_code}")
        else:
            parts.append(f"FREQ=YEARLY;INTERVAL={interval};BYMONTH={month}")

    else:
        parts.append(f"FREQ=DAILY;INTERVAL={interval}")

    # Add range
    range_type = range_.get("type", "noEnd").lower()
    if range_type == "enddate":
        end_date = range_.get("endDate", "")
        if end_date:
            # Convert to UNTIL format YYYYMMDDTHHMMSSZ
            end_dt = end_date.replace("-", "") + "T235959Z"
            parts.append(f"UNTIL={end_dt}")
    elif range_type == "numbered":
        count = range_.get("numberOfOccurrences", 1)
        parts.append(f"COUNT={count}")
    # noEnd = no UNTIL/COUNT

    return "RRULE:" + ";".join(parts)


def rrule_to_graph_recurrence(rrule_str: str, dtstart: date) -> dict:
    """Convert RRULE string to Graph patternedRecurrence dict."""
    # Strip RRULE: prefix
    if rrule_str.startswith("RRULE:"):
        rrule_str = rrule_str[6:]

    props = {}
    for part in rrule_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            props[k.strip()] = v.strip()

    freq = props.get("FREQ", "DAILY")
    interval = int(props.get("INTERVAL", 1))
    byday = props.get("BYDAY", "")
    bymonthday = props.get("BYMONTHDAY", "")
    bymonth = props.get("BYMONTH", "")
    count = props.get("COUNT")
    until = props.get("UNTIL")

    pattern = {"interval": interval}
    range_dict = {
        "startDate": dtstart.isoformat(),
        "type": "noEnd",
    }

    if freq == "DAILY":
        pattern["type"] = "daily"

    elif freq == "WEEKLY":
        pattern["type"] = "weekly"
        if byday:
            pattern["daysOfWeek"] = _rrule_days_to_graph(byday)
        pattern["firstDayOfWeek"] = "monday"

    elif freq == "MONTHLY":
        if byday and any(c.isdigit() or c in "+-" for c in byday[:-2]):
            # Relative: e.g. +2MO, -1FR
            pattern["type"] = "relativeMonthly"
            # Extract week index and day
            import re
            m = re.match(r"([+-]?\d+)([A-Z]{2})", byday)
            if m:
                week_num = int(m.group(1))
                day_code = m.group(2)
                pattern["index"] = WEEK_INDEX_REVERSE.get(week_num, "first")
                pattern["daysOfWeek"] = [RRULE_DAY_MAP.get(day_code, "monday")]
        elif bymonthday:
            pattern["type"] = "absoluteMonthly"
            pattern["dayOfMonth"] = int(bymonthday)
        else:
            pattern["type"] = "absoluteMonthly"
            pattern["dayOfMonth"] = dtstart.day

    elif freq == "YEARLY":
        if byday and bymonth:
            pattern["type"] = "relativeYearly"
            import re
            m = re.match(r"([+-]?\d+)([A-Z]{2})", byday)
            if m:
                week_num = int(m.group(1))
                day_code = m.group(2)
                pattern["index"] = WEEK_INDEX_REVERSE.get(week_num, "first")
                pattern["daysOfWeek"] = [RRULE_DAY_MAP.get(day_code, "monday")]
            pattern["month"] = int(bymonth)
        else:
            pattern["type"] = "absoluteYearly"
            if bymonthday:
                pattern["dayOfMonth"] = int(bymonthday)
            if bymonth:
                pattern["month"] = int(bymonth)

    # Set range
    if count:
        range_dict["type"] = "numbered"
        range_dict["numberOfOccurrences"] = int(count)
    elif until:
        range_dict["type"] = "endDate"
        # Parse UNTIL: YYYYMMDDTHHMMSSZ or YYYYMMDD
        until_clean = until.replace("Z", "").split("T")[0]
        y, m_str, d = until_clean[:4], until_clean[4:6], until_clean[6:8]
        range_dict["endDate"] = f"{y}-{m_str}-{d}"

    return {"pattern": pattern, "range": range_dict}
