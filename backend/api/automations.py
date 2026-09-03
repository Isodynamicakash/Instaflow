"""
InstaFlow — Automations routes
Thin proxy between the dashboard frontend and Zernio's comment-automations API.
ZERNIO_API_KEY never leaves the server; the frontend only ever talks to this app.

NOTE ON UNVERIFIED ENDPOINTS: the create + list shapes below are confirmed
against Zernio's docs. The PATCH (update/toggle) and DELETE endpoints are 
written to the same REST convention Zernio uses everywhere else in their API
(POST /v1/comment-automations, so PATCH/DELETE /v1/comment-automations/{id}
is the reasonable guess) but I have not independently confirmed those two verbs
against docs.zernio.com for this specific resource. Check the "Update
comment-automation" / "Delete comment-automation" pages there before relying
on toggle/delete in production — if the method or path differs, only this
file needs to change, nothing in the dashboard.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import httpx
import logging

from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/automations", tags=["automations"])

def zernio_headers():
    return {
        "Authorization": f"Bearer {settings.ZERNIO_API_KEY}",
        "Content-Type": "application/json",
    }

# ==================== MODELS (dashboard-shaped) ====================

class Audience(BaseModel):
    followerStatus: str = "any"     # any | follower | non_follower
    whenUnknown: str = "send"       # send | skip | verify

class FollowGate(BaseModel):
    message: str = ""
    buttonLabel: str = ""
    notFollowingMessage: str = ""

class AutomationIn(BaseModel):
    name: str
    isActive: bool = True
    trigger: str = "comment"                    # comment | story_reply
    postScope: str = "account"                  # account | post — dashboard-only concept
    platformPostId: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    matchMode: str = "word"                      # contains | word | exact
    typoTolerance: bool = True
    alsoMatchInDms: bool = False
    dmMessage: str
    commentReply: Optional[str] = ""
    audience: Audience = Audience()
    followGate: FollowGate = FollowGate()

def to_zernio_payload(a: AutomationIn) -> dict:
    payload = {
        "profileId": settings.ZERNIO_PROFILE_ID,
        "accountId": settings.ZERNIO_ACCOUNT_ID,
        "name": a.name,
        "trigger": a.trigger,
        "keywords": a.keywords,
        "matchMode": a.matchMode,
        "typoTolerance": a.typoTolerance,
        "alsoMatchInDms": a.alsoMatchInDms,
        "dmMessage": a.dmMessage,
        "commentReply": a.commentReply or "",
        "audience": a.audience.model_dump(),
    }
    if a.postScope == "post" and a.platformPostId:
        payload["platformPostId"] = a.platformPostId
    if a.audience.followerStatus != "any" and a.audience.whenUnknown == "verify":
        payload["followGate"] = a.followGate.model_dump()
    return payload

def from_zernio(obj: dict) -> dict:
    """Reshape a Zernio automation object into what the dashboard renders."""
    return {
        "id": obj.get("id"),
        "name": obj.get("name", ""),
        "isActive": obj.get("isActive", True),
        "trigger": obj.get("trigger", "comment"),
        "postScope": "post" if obj.get("platformPostId") else "account",
        "platformPostId": obj.get("platformPostId"),
        "postCaption": obj.get("postTitle"),
        "keywords": obj.get("keywords", []),
        "matchMode": obj.get("matchMode", "word"),
        "typoTolerance": obj.get("typoTolerance", False),
        "alsoMatchInDms": obj.get("alsoMatchInDms", False),
        "dmMessage": obj.get("dmMessage", ""),
        "commentReply": obj.get("commentReply", ""),
        "audience": obj.get("audience") or {"followerStatus": "any", "whenUnknown": "send"},
        "followGate": obj.get("followGate") or {"message": "", "buttonLabel": "", "notFollowingMessage": ""},
        "stats": obj.get("stats") or {"totalTriggered": 0, "totalSent": 0, "totalFailed": 0},
    }

def _raise(e: httpx.HTTPStatusError):
    logger.error(f"❌ Zernio call failed [{e.response.status_code}]: {e.response.text}")
    raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

# ==================== ROUTES ====================

@router.get("")
async def list_automations():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.ZERNIO_API_BASE}/v1/comment-automations",
                headers=zernio_headers(),
                params={"profileId": settings.ZERNIO_PROFILE_ID, "accountId": settings.ZERNIO_ACCOUNT_ID},
                timeout=15.0,
            )
            r.raise_for_status()
            data = r.json()
            automations = data.get("automations") or data.get("data") or []
            return [from_zernio(a) for a in automations]
    except httpx.HTTPStatusError as e:
        _raise(e)
    except Exception as e:
        logger.error(f"❌ List automations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_automation(automation: AutomationIn):
    if automation.postScope == "post" and not automation.platformPostId:
        raise HTTPException(status_code=400, detail="platformPostId is required when postScope is 'post'")
    try:
        payload = to_zernio_payload(automation)
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{settings.ZERNIO_API_BASE}/v1/comment-automations",
                headers=zernio_headers(),
                json=payload,
                timeout=15.0,
            )
            r.raise_for_status()
            data = r.json()
            return from_zernio(data.get("automation") or data)
    except httpx.HTTPStatusError as e:
        _raise(e)
    except Exception as e:
        logger.error(f"❌ Create automation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{automation_id}")
async def update_automation(automation_id: str, automation: AutomationIn):
    """UNVERIFIED endpoint shape — see module docstring."""
    try:
        payload = to_zernio_payload(automation)
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{settings.ZERNIO_API_BASE}/v1/comment-automations/{automation_id}",
                headers=zernio_headers(),
                json=payload,
                timeout=15.0,
            )
            r.raise_for_status()
            data = r.json()
            return from_zernio(data.get("automation") or data)
    except httpx.HTTPStatusError as e:
        _raise(e)
    except Exception as e:
        logger.error(f"❌ Update automation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{automation_id}/toggle")
async def toggle_automation(automation_id: str, is_active: bool):
    """Convenience endpoint so the dashboard's on/off switch is a 1-field
    PATCH instead of resending the whole automation. UNVERIFIED — see module docstring."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{settings.ZERNIO_API_BASE}/v1/comment-automations/{automation_id}",
                headers=zernio_headers(),
                json={"isActive": is_active},
                timeout=15.0,
            )
            r.raise_for_status()
            data = r.json()
            return from_zernio(data.get("automation") or data)
    except httpx.HTTPStatusError as e:
        _raise(e)
    except Exception as e:
        logger.error(f"❌ Toggle automation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{automation_id}")
async def delete_automation(automation_id: str):
    """UNVERIFIED endpoint shape — see module docstring."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.delete(
                f"{settings.ZERNIO_API_BASE}/v1/comment-automations/{automation_id}",
                headers=zernio_headers(),
                timeout=15.0,
            )
            r.raise_for_status()
            return {"status": "ok", "deleted": automation_id}
    except httpx.HTTPStatusError as e:
        _raise(e)
    except Exception as e:
        logger.error(f"❌ Delete automation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
