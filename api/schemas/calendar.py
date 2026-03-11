import uuid
from typing import Optional
from pydantic import BaseModel


class CalendarResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    external_calendar_id: str
    name: str
    is_active: bool
    is_default: bool
    is_mirror_enabled: bool
    timezone: Optional[str]
    account_email: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_calendar(cls, cal) -> "CalendarResponse":
        data = {
            "id": cal.id,
            "account_id": cal.account_id,
            "external_calendar_id": cal.external_calendar_id,
            "name": cal.name,
            "is_active": cal.is_active,
            "is_default": cal.is_default,
            "is_mirror_enabled": cal.is_mirror_enabled,
            "timezone": cal.timezone,
            "account_email": cal.account.email if cal.account else None,
        }
        return cls(**data)


class CalendarPatch(BaseModel):
    is_active: Optional[bool] = None
    is_mirror_enabled: Optional[bool] = None
