"""Pydantic schemas for Posts and Metrics."""
from pydantic import BaseModel
from typing import Optional


class PostMetric(BaseModel):
    post_id: str
    caption: str = ""
    media_type: str = "IMAGE"
    timestamp: str = ""
    likes: int = 0
    comments: int = 0
    impressions: int = 0
    reach: int = 0
    saved: int = 0
    shares: int = 0
