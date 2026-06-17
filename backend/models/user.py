"""Pydantic schemas for Users."""
from pydantic import BaseModel
from typing import Optional


class UserOnboardRequest(BaseModel):
    access_token: str
    ig_user_id: str
    ig_username: Optional[str] = ""
    whatsapp_number: Optional[str] = ""
    form_data: Optional[dict] = {}  # niche, tone, goals, content_type


class UserOnboardResponse(BaseModel):
    user_id: str
    profile: dict
    posts_analyzed: int
    analysis: dict
    report: str
