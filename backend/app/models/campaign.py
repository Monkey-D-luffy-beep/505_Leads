from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CampaignBase(BaseModel):
    name: str
    description: Optional[str] = None
    target_filters: dict = {}
    min_score: int = 30
    signal_weights: dict = {}
    status: str = "draft"
    send_mode: str = "review"
    daily_limit: int = 30
    send_window_start: str = "09:00"
    send_window_end: str = "17:00"
    timezone: str = "UTC"


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_filters: Optional[dict] = None
    min_score: Optional[int] = None
    signal_weights: Optional[dict] = None
    status: Optional[str] = None
    send_mode: Optional[str] = None
    daily_limit: Optional[int] = None
    send_window_start: Optional[str] = None
    send_window_end: Optional[str] = None
    timezone: Optional[str] = None


class CampaignResponse(CampaignBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
