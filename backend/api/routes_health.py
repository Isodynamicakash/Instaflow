"""Health check route."""

from datetime import datetime
from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/api/health")
async def health():
    return {"status": "running", "timestamp": datetime.now().isoformat()}
