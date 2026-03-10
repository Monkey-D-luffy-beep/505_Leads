from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EmailLogBase(BaseModel):
    campaign_lead_id: str
    contact_id: str
    sequence_id: str
    variant_sent: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    status: str = "queued"
    tracking_id: Optional[str] = None


class EmailLogCreate(EmailLogBase):
    pass


class EmailLogUpdate(BaseModel):
    status: Optional[str] = None
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None


class EmailLogResponse(EmailLogBase):
    id: str
    queued_at: datetime
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None

    class Config:
        from_attributes = True
