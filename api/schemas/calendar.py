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

    model_config = {"from_attributes": True}


class CalendarPatch(BaseModel):
    is_active: Optional[bool] = None
    is_mirror_enabled: Optional[bool] = None
