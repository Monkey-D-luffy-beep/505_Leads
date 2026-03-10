from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class LeadBase(BaseModel):
    company_name: str
    website: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    google_rating: Optional[float] = None
    google_review_count: Optional[int] = None
    employee_estimate: Optional[str] = None
    lead_score: int = 0
    score_breakdown: dict = {}
    status: str = "new"
    notes: Optional[str] = None
    tags: List[str] = []
    raw_data: dict = {}


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    company_name: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    google_rating: Optional[float] = None
    google_review_count: Optional[int] = None
    employee_estimate: Optional[str] = None
    lead_score: Optional[int] = None
    score_breakdown: Optional[dict] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    raw_data: Optional[dict] = None


class LeadResponse(LeadBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
