from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ReplyBase(BaseModel):
    email_log_id: str
    contact_id: str
    subject: Optional[str] = None
    body: Optional[str] = None
    sentiment: Optional[str] = None
    is_read: bool = False
    raw_payload: dict = {}


class ReplyCreate(ReplyBase):
    pass


class ReplyUpdate(BaseModel):
    sentiment: Optional[str] = None
    is_read: Optional[bool] = None


class ReplyResponse(ReplyBase):
    id: str
    received_at: datetime

    class Config:
        from_attributes = True
