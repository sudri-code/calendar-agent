from typing import Optional
from pydantic import BaseModel


class GraphResourceData(BaseModel):
    id: Optional[str] = None
    odata_type: Optional[str] = None
    odata_id: Optional[str] = None
    odata_etag: Optional[str] = None


class GraphNotification(BaseModel):
    id: str
    subscription_id: str
    subscription_expiration_date_time: Optional[str] = None
    change_type: str
    resource: str
    resource_data: Optional[GraphResourceData] = None
    client_state: Optional[str] = None
    tenant_id: Optional[str] = None
    sequence_number: Optional[int] = None


class GraphNotificationPayload(BaseModel):
    value: list[GraphNotification]
