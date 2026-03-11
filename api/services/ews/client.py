"""
EWS client factory using exchangelib.
exchangelib is synchronous — all calls must be wrapped in run_in_executor.
"""
import asyncio
from functools import partial
from typing import Any, Callable

import structlog
from exchangelib import (
    Account,
    Configuration,
    Credentials,
    DELEGATE,
    NTLM,
    BASIC,
)
from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter

from api.config import settings
from api.exceptions import AuthExpiredError, InsufficientPermissionsError

logger = structlog.get_logger()

AUTH_TYPE_MAP = {
    "NTLM": NTLM,
    "basic": BASIC,
}


def _build_account(account_model) -> Account:
    """Build a synchronous exchangelib Account from the DB model."""
    auth_type = AUTH_TYPE_MAP.get(account_model.auth_type, NTLM)

    credentials = Credentials(
        username=account_model.username,
        password=account_model.password,
    )
    config = Configuration(
        server=account_model.ews_server,
        credentials=credentials,
        auth_type=auth_type,
    )

    if settings.ews_verify_ssl is False:
        # Allow self-signed certs in corporate environments
        BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter

    try:
        return Account(
            primary_smtp_address=account_model.email,
            config=config,
            autodiscover=False,
            access_type=DELEGATE,
        )
    except Exception as e:
        if "401" in str(e) or "Unauthorized" in str(e):
            raise AuthExpiredError(f"EWS auth failed for {account_model.email}: {e}")
        if "403" in str(e) or "Forbidden" in str(e):
            raise InsufficientPermissionsError(f"EWS access denied for {account_model.email}: {e}")
        raise


async def run_ews(fn: Callable, *args, **kwargs) -> Any:
    """Run a synchronous EWS call in the default thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(fn, *args, **kwargs))


class EWSClient:
    """Async-friendly wrapper around a synchronous exchangelib Account."""

    def __init__(self, account_model):
        self._model = account_model
        self._account: Account | None = None

    def _get_account(self) -> Account:
        if self._account is None:
            self._account = _build_account(self._model)
        return self._account

    async def get_calendars(self) -> list[dict]:
        def _fetch():
            acc = self._get_account()
            # exchangelib exposes the primary calendar; sub-folders are children
            calendars = []
            root_cal = acc.calendar
            calendars.append({
                "id": str(root_cal.id),
                "name": root_cal.name,
                "is_default": True,
            })
            for folder in root_cal.children:
                calendars.append({
                    "id": str(folder.id),
                    "name": folder.name,
                    "is_default": False,
                })
            return calendars

        return await run_ews(_fetch)

    async def get_contacts(self) -> list[dict]:
        def _fetch():
            acc = self._get_account()
            contacts = []
            for contact in acc.contacts.all():
                emails = []
                if hasattr(contact, "email_addresses") and contact.email_addresses:
                    emails = [e.email for e in contact.email_addresses if e and e.email]
                contacts.append({
                    "id": getattr(contact, "id", ""),
                    "displayName": getattr(contact, "display_name", "") or "",
                    "emailAddresses": [{"address": e} for e in emails],
                    "mobilePhone": getattr(contact, "mobile_phone", None),
                })
            return contacts

        return await run_ews(_fetch)

    async def get_events(self, folder_id: str, start, end, timezone_str: str = "UTC") -> list[dict]:
        def _fetch():
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(timezone_str)
            acc = self._get_account()
            # Resolve folder: default calendar or sub-folder by id
            folder = acc.calendar
            if folder_id and folder_id != str(acc.calendar.id):
                for child in acc.calendar.children:
                    if str(child.id) == folder_id:
                        folder = child
                        break

            items = folder.view(start=start, end=end)
            result = []
            for item in items:
                result.append(_calendar_item_to_dict(item, tz))
            return result

        return await run_ews(_fetch)

    async def create_event(self, folder_id: str, data: dict):
        def _fetch():
            from exchangelib import CalendarItem, EWSDateTime, Attendee, Mailbox
            from exchangelib.items import SEND_TO_ALL_AND_SAVE_COPY

            acc = self._get_account()
            folder = acc.calendar
            if folder_id and folder_id != str(acc.calendar.id):
                for child in acc.calendar.children:
                    if str(child.id) == folder_id:
                        folder = child
                        break

            attendees = [
                Attendee(mailbox=Mailbox(email_address=a["email"]))
                for a in data.get("attendees", [])
                if a.get("email")
            ]

            item = CalendarItem(
                folder=folder,
                subject=data["subject"],
                body=data.get("body", ""),
                start=data["start"],
                end=data["end"],
                is_all_day=False,
                required_attendees=attendees if attendees else None,
            )

            if data.get("recurrence"):
                item.recurrence = data["recurrence"]

            item.save(send_meeting_invitations=SEND_TO_ALL_AND_SAVE_COPY)
            return _calendar_item_to_dict(item)

        return await run_ews(_fetch)

    async def update_event(self, item_id: str, change_key: str, data: dict):
        def _fetch():
            from exchangelib import CalendarItem, EWSDateTime
            from exchangelib.items import SEND_TO_ALL_AND_SAVE_COPY
            from exchangelib.restriction import Restriction

            acc = self._get_account()
            items = list(acc.calendar.filter(id=item_id))
            if not items:
                raise ValueError(f"Event {item_id} not found")

            item = items[0]
            if "subject" in data:
                item.subject = data["subject"]
            if "body" in data:
                item.body = data["body"]
            if "start" in data:
                item.start = data["start"]
            if "end" in data:
                item.end = data["end"]

            item.save(send_meeting_invitations=SEND_TO_ALL_AND_SAVE_COPY)
            return _calendar_item_to_dict(item)

        return await run_ews(_fetch)

    async def delete_event(self, item_id: str):
        def _fetch():
            from exchangelib.items import SEND_TO_ALL_AND_SAVE_COPY

            acc = self._get_account()
            items = list(acc.calendar.filter(id=item_id))
            if items:
                items[0].delete(send_meeting_cancellations=SEND_TO_ALL_AND_SAVE_COPY)

        return await run_ews(_fetch)

    async def get_free_busy(self, emails: list[str], start, end) -> list[dict]:
        def _fetch():
            from exchangelib.services import GetUserAvailability
            from exchangelib.properties import MailboxData, FreeBusyView, FreeBusyViewOptions

            acc = self._get_account()
            mailboxes = [MailboxData(email=email) for email in emails]
            options = FreeBusyViewOptions(
                time_window={"StartTime": start, "EndTime": end},
                requested_view="FreeBusy",
            )
            try:
                result = acc.protocol.get_free_busy_info(
                    accounts=[(acc, "Organizer", False)] + [(None, None, False)] * (len(emails) - 1),
                    start=start,
                    end=end,
                    merged_free_busy_interval=30,
                    requested_view="FreeBusy",
                )
                return list(result)
            except Exception:
                return []

        return await run_ews(_fetch)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _calendar_item_to_dict(item, local_tz=None) -> dict:
    """Convert exchangelib CalendarItem to a plain dict.
    local_tz: zoneinfo.ZoneInfo to convert times into (default: UTC).
    """
    def _fmt(ews_dt):
        if ews_dt is None:
            return None
        dt = ews_dt.astimezone(local_tz) if local_tz else ews_dt
        return dt.isoformat()

    attendees = []
    for field in ("required_attendees", "optional_attendees"):
        group = getattr(item, field, None) or []
        for a in group:
            mb = getattr(a, "mailbox", None)
            if mb:
                name = getattr(mb, "name", "") or ""
                email = getattr(mb, "email_address", "") or ""
                if email:
                    attendees.append({"name": name, "email": email})

    return {
        "id": getattr(item, "id", ""),
        "changeKey": getattr(item, "changekey", ""),
        "subject": getattr(item, "subject", "") or "",
        "body": str(getattr(item, "body", "") or ""),
        "start": _fmt(item.start),
        "end": _fmt(item.end),
        "attendees": attendees,
        "isRecurring": getattr(item, "is_recurring", False),
        "recurrence": getattr(item, "recurrence", None),
        "type": getattr(item, "type", "singleInstance"),
        "seriesMasterId": getattr(item, "series_master_item_id", {}).get("id") if hasattr(item, "series_master_item_id") and item.series_master_item_id else None,
    }
