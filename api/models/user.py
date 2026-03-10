import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Text, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base, uuid_pk, timestamp_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    # Relationships
    exchange_accounts: Mapped[list["ExchangeAccount"]] = relationship("ExchangeAccount", back_populates="user", cascade="all, delete-orphan")
    calendars: Mapped[list["Calendar"]] = relationship("Calendar", back_populates="user", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship("Event", back_populates="user", cascade="all, delete-orphan")
    sync_groups: Mapped[list["SyncGroup"]] = relationship("SyncGroup", back_populates="user", cascade="all, delete-orphan")
