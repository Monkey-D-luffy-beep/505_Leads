from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SequenceBase(BaseModel):
    campaign_id: str
    step_number: int
    step_name: Optional[str] = None
    delay_days: int = 0
    variant_a_subject: Optional[str] = None
    variant_a_body: Optional[str] = None
    variant_b_subject: Optional[str] = None
    variant_b_body: Optional[str] = None
    split_ratio: float = 0.5
    winner_variant: Optional[str] = None


class SequenceCreate(SequenceBase):
    pass


class SequenceUpdate(BaseModel):
    step_number: Optional[int] = None
    step_name: Optional[str] = None
    delay_days: Optional[int] = None
    variant_a_subject: Optional[str] = None
    variant_a_body: Optional[str] = None
    variant_b_subject: Optional[str] = None
    variant_b_body: Optional[str] = None
    split_ratio: Optional[float] = None
    winner_variant: Optional[str] = None


class SequenceResponse(SequenceBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True
