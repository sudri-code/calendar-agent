import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base
from api.utils.encryption import encrypt, decrypt


class ExchangeAccount(Base):
    __tablename__ = "exchange_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # EWS connection
    ews_server: Mapped[str] = mapped_column(Text, nullable=False)          # e.g. "mail.company.ru"
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)        # Windows domain, e.g. "CORP"
    username_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # DOMAIN\user or UPN
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="NTLM")  # NTLM | basic | kerberos
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="exchange_accounts")
    calendars: Mapped[list["Calendar"]] = relationship("Calendar", back_populates="account", cascade="all, delete-orphan")

    @property
    def username(self) -> str:
        return decrypt(self.username_encrypted)

    @username.setter
    def username(self, value: str) -> None:
        self.username_encrypted = encrypt(value)

    @property
    def password(self) -> str:
        return decrypt(self.password_encrypted)

    @password.setter
    def password(self, value: str) -> None:
        self.password_encrypted = encrypt(value)
