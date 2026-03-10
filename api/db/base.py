import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


uuid_pk = Annotated[
    uuid.UUID,
    mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
]

timestamp_now = Annotated[
    datetime,
    mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()")),
]


class Base(DeclarativeBase):
    pass
