from datetime import datetime

from api.services.ews.client import EWSClient, run_ews


async def get_schedule(account, emails: list[str], start: datetime, end: datetime, timezone: str = "UTC") -> dict:
    """Get free/busy schedule via EWS GetUserAvailability."""
    from exchangelib import EWSDateTime, EWSTimeZone

    tz = EWSTimeZone.timezone(timezone)
    ews_start = EWSDateTime.from_datetime(start).replace(tzinfo=tz)
    ews_end = EWSDateTime.from_datetime(end).replace(tzinfo=tz)

    def _fetch():
        from exchangelib import Account, Configuration, Credentials, NTLM, DELEGATE
        from api.utils.encryption import decrypt

        credentials = Credentials(username=account.username, password=account.password)
        from exchangelib.protocol import BaseProtocol
        config = Configuration(
            server=account.ews_server,
            credentials=credentials,
            auth_type=NTLM,
        )
        acc = Account(
            primary_smtp_address=account.email,
            config=config,
            autodiscover=False,
            access_type=DELEGATE,
        )
        try:
            result = acc.protocol.get_free_busy_info(
                accounts=[(acc, "Organizer", False)],
                start=ews_start,
                end=ews_end,
                merged_free_busy_interval=30,
                requested_view="FreeBusy",
            )
            schedules = []
            for attendee_info, free_busy in zip(emails, result):
                busy_items = []
                if hasattr(free_busy, "calendar_event_array") and free_busy.calendar_event_array:
                    for ev in free_busy.calendar_event_array:
                        busy_items.append({
                            "start": {"dateTime": str(ev.start)},
                            "end": {"dateTime": str(ev.end)},
                            "status": "busy",
                        })
                schedules.append({
                    "scheduleId": attendee_info,
                    "scheduleItems": busy_items,
                })
            return {"value": schedules}
        except Exception:
            return {"value": []}

    return await run_ews(_fetch)
