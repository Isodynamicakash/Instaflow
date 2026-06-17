"""
WhatsApp Webhook — Phase 2.
Handles content approval replies and escalation responses.
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from backend.config import settings

router = APIRouter(tags=["webhooks"])


@router.get("/webhook/whatsapp")
async def verify_whatsapp(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WA_WEBHOOK_VERIFY_TOKEN:
        return int(challenge)
    raise HTTPException(403, "Verification failed")


@router.post("/webhook/whatsapp")
async def handle_whatsapp(request: Request):
    """Phase 2: process approval replies from WhatsApp."""
    body = await request.json()
    print(f"📱 WhatsApp webhook (stub): {str(body)[:200]}")
    return JSONResponse({"status": "ok"})
