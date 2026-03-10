import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AccountResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: Optional[str]
    ews_server: str
    domain: Optional[str]
    auth_type: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AddAccountRequest(BaseModel):
    email: str
    ews_server: str              # e.g. "mail.company.ru"
    username: str                # e.g. "CORP\\ivanov" or "ivanov@company.ru"
    password: str
    domain: Optional[str] = None
    auth_type: str = "NTLM"     # NTLM | basic
    display_name: Optional[str] = None
