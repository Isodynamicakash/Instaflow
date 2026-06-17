"""Pydantic schemas for Content Queue."""
from pydantic import BaseModel
from typing import Optional


class ContentOption(BaseModel):
    caption: str
    hashtags: list[str] = []
    content_type: str = ""
    best_time: str = ""
    why: str = ""


class ContentGenerateRequest(BaseModel):
    user_id: str
    top_hashtags: list[str] = []
    top_themes: list[str] = []


class ContentGenerateResponse(BaseModel):
    options: list[ContentOption]
    status: str = "generated"
