import uuid
from typing import Optional
from pydantic import BaseModel


class ContactResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: Optional[str]
    phone: Optional[str]
    source: str
    merged_contact_key: Optional[str]

    model_config = {"from_attributes": True}
