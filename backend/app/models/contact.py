from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class ContactBase(BaseModel):
    lead_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[EmailStr] = None
    email_confidence: Optional[int] = None
    email_status: str = "unverified"
    linkedin_url: Optional[str] = None


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[EmailStr] = None
    email_confidence: Optional[int] = None
    email_status: Optional[str] = None
    linkedin_url: Optional[str] = None


class ContactResponse(ContactBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True
