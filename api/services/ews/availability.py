from datetime import datetime

import structlog

from api.services.ews.client import run_ews
from api.services.ews.client import _build_account

logger = structlog.get_logger()


async def get_schedule(account, emails: list[str], start: datetime, end: datetime, timezone: str = "UTC") -> dict:
    """Get free/busy schedule via EWS GetUserAvailability."""
    from exchangelib import EWSDateTime, UTC

    ews_start = EWSDateTime.from_datetime(start).replace(tzinfo=UTC)
    ews_end = EWSDateTime.from_datetime(end).replace(tzinfo=UTC)

    def _fetch():
        acc = _build_account(account)

        # Build deduplicated list: organizer first, then other emails
        seen = {account.email.lower()}
        all_emails = [account.email]
        for e in emails:
            if e.lower() not in seen:
                seen.add(e.lower())
                all_emails.append(e)

        # accounts list: (Account_or_email_str, meeting_request_type, exclude_conflicts)
        accounts_list = [(acc, "Organizer", False)]
        for email in all_emails[1:]:
            accounts_list.append((email, "Required", False))

        try:
            result = list(acc.protocol.get_free_busy_info(
                accounts=accounts_list,
                start=ews_start,
                end=ews_end,
                merged_free_busy_interval=30,
                requested_view="FreeBusy",
            ))
            schedules = []
            for email, free_busy in zip(all_emails, result):
                busy_items = []
                cal_events = getattr(free_busy, "calendar_events", None) or []
                for ev in cal_events:
                    busy_type = (getattr(ev, "busy_type", None) or "Busy").lower()
                    if busy_type == "free":
                        continue
                    busy_items.append({
                        "start": {"dateTime": ev.start.isoformat()},
                        "end": {"dateTime": ev.end.isoformat()},
                        "status": busy_type,
                    })
                schedules.append({
                    "scheduleId": email,
                    "scheduleItems": busy_items,
                })
            return {"value": schedules}
        except Exception as e:
            logger.error("get_free_busy_info failed", error=str(e), emails=all_emails)
            return {"value": []}

    return await run_ews(_fetch)
