import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import async_session_factory
from api.models.contact import Contact
from api.models.exchange_account import ExchangeAccount
from api.services.graph.contacts import list_contacts

logger = structlog.get_logger()


def _normalize_name(name: str) -> str:
    return name.lower().strip()


def _normalize_email(email: str) -> str:
    return email.lower().strip()


def _merged_contact_key(email: str) -> str:
    """Generate deterministic UUID from email."""
    normalized = _normalize_email(email)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"contact:{normalized}"))


async def sync_contacts(user_id: uuid.UUID) -> int:
    """Sync contacts from all Exchange accounts, merging duplicates by email."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.user_id == user_id,
                ExchangeAccount.status == "active",
            )
        )
        accounts = result.scalars().all()

        total = 0
        for account in accounts:
            try:
                graph_contacts = await list_contacts(account)

                for gc in graph_contacts:
                    emails = gc.get("emailAddresses", [])
                    primary_email = emails[0]["address"] if emails else None
                    name = gc.get("displayName", "Unknown")

                    # Check if contact exists
                    existing_result = await session.execute(
                        select(Contact).where(
                            Contact.account_id == account.id,
                            Contact.external_contact_id == gc["id"],
                        )
                    )
                    contact = existing_result.scalar_one_or_none()

                    merged_key = _merged_contact_key(primary_email) if primary_email else None

                    if contact:
                        contact.name = name
                        contact.normalized_name = _normalize_name(name)
                        contact.email = primary_email
                        contact.merged_contact_key = merged_key
                        contact.updated_at = datetime.now(timezone.utc)
                    else:
                        contact = Contact(
                            user_id=user_id,
                            account_id=account.id,
                            external_contact_id=gc["id"],
                            name=name,
                            normalized_name=_normalize_name(name),
                            email=primary_email,
                            phone=gc.get("mobilePhone") or (gc.get("businessPhones") or [None])[0],
                            source=account.email,
                            merged_contact_key=merged_key,
                        )
                        session.add(contact)

                    total += 1

                logger.info(
                    "Contacts synced",
                    account_email=account.email,
                    count=len(graph_contacts),
                )
            except Exception as e:
                logger.error(
                    "Failed to sync contacts",
                    account_email=account.email,
                    error=str(e),
                )

        await session.commit()
        return total


async def search_contacts(user_id: uuid.UUID, q: str) -> list[Contact]:
    """Search contacts by name or email (case-insensitive)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Contact).where(
                Contact.user_id == user_id,
                or_(
                    Contact.name.ilike(f"%{q}%"),
                    Contact.email.ilike(f"%{q}%"),
                    Contact.normalized_name.ilike(f"%{q}%"),
                ),
            ).limit(20)
        )
        return result.scalars().all()
