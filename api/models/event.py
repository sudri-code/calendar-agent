import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Text, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    calendar_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("calendars.id", ondelete="CASCADE"), nullable=False)
    external_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    sync_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_groups.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    attendees_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_change_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Recurrence fields
    recurrence_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recurrence_master_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True
    )
    is_recurrence_master: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    recurrence_exception_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_cancelled_occurrence: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    instance_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="events")
    calendar: Mapped["Calendar"] = relationship("Calendar", back_populates="events")
    sync_group: Mapped["SyncGroup"] = relationship("SyncGroup", back_populates="events", foreign_keys=[sync_group_id])
    recurrence_master: Mapped["Event | None"] = relationship("Event", remote_side="Event.id", foreign_keys=[recurrence_master_id])
