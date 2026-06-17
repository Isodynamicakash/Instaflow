# backend/main.py
"""
InstaFlow — Main Server Entrypoint
Simple, focused: Just webhook + health checks.

Run: uvicorn backend.main:app --reload --port 8000
Deploy: Railway / Render / AWS
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from backend.config import settings

# ── Webhooks ──
from backend.webhooks.instagram import router as ig_webhook_router

# ── Setup logging ──
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("="*70)
    logger.info("🚀 InstaFlow Agent — Server Started")
    logger.info(f"   Environment: {settings.ENV}")
    logger.info(f"   IG User ID: {settings.IG_USER_ID or '(not set)'}")
    logger.info(f"   Claude Model: {settings.CLAUDE_MODEL}")
    logger.info(f"   Webhook: POST /webhook/instagram")
    logger.info("="*70)
    
    yield
    
    # Shutdown
    logger.info("🛑 InstaFlow Agent — Server Stopped")


# ── Create App ──
app = FastAPI(
    title="InstaFlow Agent",
    description="Real-time Instagram AI engagement agent",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Webhooks ──
app.include_router(ig_webhook_router)


# ── Root Endpoint ──
@app.get("/")
async def root():
    return {
        "name": "InstaFlow Agent",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "root": "/",
            "health": "/health",
            "webhook": "/webhook/instagram",
            "docs": "/docs"
        }
    }


# ── Health Check ──
@app.get("/health")
async def health():
    from datetime import datetime
    return {
        "status": "healthy",
        "service": "instaflow",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENV
    }


# ── Error Handler ──
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return {
        "status": "error",
        "message": str(exc)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )