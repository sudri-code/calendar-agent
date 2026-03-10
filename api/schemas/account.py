import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AccountResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: Optional[str]
    status: str
    token_expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class OAuthStartResponse(BaseModel):
    auth_url: str
    state: str


class OAuthCallbackParams(BaseModel):
    code: str
    state: str
    error: Optional[str] = None
    error_description: Optional[str] = None
