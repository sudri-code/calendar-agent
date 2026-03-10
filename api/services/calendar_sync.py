import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import async_session_factory
from api.models.calendar import Calendar
from api.models.exchange_account import ExchangeAccount
from api.models.user import User
from api.services.ews.calendars import list_calendars

logger = structlog.get_logger()


async def sync_calendars(user_id: uuid.UUID) -> list[Calendar]:
    """Sync calendars from all Exchange accounts for a user."""
    async with async_session_factory() as session:
        # Get all active accounts
        result = await session.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.user_id == user_id,
                ExchangeAccount.status == "active",
            )
        )
        accounts = result.scalars().all()

        synced = []
        for account in accounts:
            try:
                graph_calendars = await list_calendars(account)
                for gc in graph_calendars:
                    cal_result = await session.execute(
                        select(Calendar).where(
                            Calendar.account_id == account.id,
                            Calendar.external_calendar_id == gc["id"],
                        )
                    )
                    cal = cal_result.scalar_one_or_none()

                    if cal:
                        cal.name = gc.get("name", cal.name)
                        cal.updated_at = datetime.now(timezone.utc)
                    else:
                        cal = Calendar(
                            user_id=user_id,
                            account_id=account.id,
                            external_calendar_id=gc["id"],
                            name=gc.get("name", "Unknown"),
                            is_default=gc.get("is_default", False),
                        )
                        session.add(cal)

                    synced.append(cal)

                logger.info(
                    "Calendars synced",
                    account_email=account.email,
                    count=len(graph_calendars),
                )
            except Exception as e:
                logger.error(
                    "Failed to sync calendars for account",
                    account_email=account.email,
                    error=str(e),
                )

        await session.commit()
        return synced
