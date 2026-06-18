"""
InstaFlow — Main Server Entrypoint
Webhooks + Dashboard API
Run: uvicorn backend.main:app --reload --port 8000
Deploy: Railway / Render / AWS
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import asyncio
import httpx
from anthropic import Anthropic
from datetime import datetime

from backend.config import settings
from backend.webhooks.instagram import router as ig_webhook_router

# ── Setup logging ──
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

class SchedulePostRequest(BaseModel):
    caption: str
    hashtags: str = ""
    scheduledTime: str
    useAI: bool = False

class CaptionRequest(BaseModel):
    prompt: str

class HashtagsRequest(BaseModel):
    topic: str

# ==================== INSTAGRAM API CLIENT ====================

class InstagramAPI:
    def __init__(self, access_token: str, user_id: str, api_base: str):
        self.access_token = access_token
        self.user_id = user_id
        self.api_base = api_base
        self.client = httpx.AsyncClient()

    async def get_posts(self):
        """Get user's recent posts"""
        try:
            url = f"{self.api_base}/{self.user_id}/media"
            params = {
                "fields": "id,caption,timestamp,like_count,comments_count,media_type",
                "access_token": self.access_token,
            }
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"✅ Fetched {len(data.get('data', []))} posts")
            return data.get("data", [])
        except Exception as e:
            logger.error(f"❌ Failed to get posts: {e}")
            return []

    async def get_comments(self):
        """Get recent comments"""
        try:
            posts = await self.get_posts()
            all_comments = []
            for post in posts[:5]:
                url = f"{self.api_base}/{post['id']}/comments"
                params = {
                    "fields": "id,from,text,timestamp",
                    "access_token": self.access_token,
                }
                response = await self.client.get(url, params=params)
                if response.status_code == 200:
                    comments = response.json().get("data", [])
                    all_comments.extend(comments)
            logger.info(f"✅ Fetched {len(all_comments)} comments")
            return all_comments
        except Exception as e:
            logger.error(f"❌ Failed to get comments: {e}")
            return []

    async def close(self):
        await self.client.aclose()

# Initialize API
ig_api = InstagramAPI(settings.IG_ACCESS_TOKEN, settings.IG_USER_ID, settings.IG_API_BASE)

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
    logger.info(f"   Dashboard: /analytics, /posts/schedule, /ai/caption, etc.")
    logger.info("="*70)
    
    yield
    
    # Shutdown
    await ig_api.close()
    logger.info("🛑 InstaFlow Agent — Server Stopped")

# ── Create App ──
app = FastAPI(
    title="InstaFlow Agent",
    description="Real-time Instagram AI engagement agent + Dashboard",
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

# ==================== WEBHOOKS (EXISTING) ====================
# Keep all your existing webhook functionality
app.include_router(ig_webhook_router)

# ==================== DASHBOARD ENDPOINTS (NEW) ====================

# In-memory storage for scheduled posts
scheduled_posts = []

# ── Health & Root ──
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
            "dashboard": {
                "analytics": "/analytics",
                "schedule": "/posts/schedule",
                "scheduled": "/posts/scheduled",
                "comments": "/comments",
                "ai_caption": "/ai/caption",
                "ai_hashtags": "/ai/hashtags",
                "websocket": "/ws/analytics"
            },
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "instaflow",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENV
    }

# ==================== ANALYTICS ====================

@app.get("/analytics")
async def get_analytics():
    """Get real analytics from Instagram"""
    try:
        posts = await ig_api.get_posts()
        comments = await ig_api.get_comments()
        
        total_likes = sum(p.get("like_count", 0) for p in posts)
        total_comments = sum(p.get("comments_count", 0) for p in posts)
        
        logger.info(f"📊 Analytics: {len(posts)} posts, {total_likes} likes, {total_comments} comments")
        
        return {
            "totalPosts": len(posts),
            "totalLikes": total_likes,
            "totalComments": total_comments,
            "recentEngagement": comments[:10]
        }
    except Exception as e:
        logger.error(f"❌ Analytics error: {e}")
        return {
            "totalPosts": 0,
            "totalLikes": 0,
            "totalComments": 0,
            "recentEngagement": []
        }

# ==================== SCHEDULING ====================

@app.post("/posts/schedule")
async def schedule_post(post: SchedulePostRequest):
    """Schedule a post"""
    try:
        scheduled_post = {
            "id": len(scheduled_posts) + 1,
            "caption": post.caption,
            "hashtags": post.hashtags,
            "scheduledTime": post.scheduledTime,
            "useAI": post.useAI,
            "status": "scheduled",
            "createdAt": datetime.now().isoformat()
        }
        
        scheduled_posts.append(scheduled_post)
        logger.info(f"📅 Post scheduled for {post.scheduledTime}")
        
        return {
            "success": True,
            "post": scheduled_post,
            "message": f"Post scheduled for {post.scheduledTime}"
        }
    except Exception as e:
        logger.error(f"❌ Schedule error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/posts/scheduled")
async def get_scheduled_posts():
    """Get all scheduled posts"""
    try:
        logger.info(f"📅 Retrieved {len(scheduled_posts)} scheduled posts")
        return {
            "data": scheduled_posts,
            "total": len(scheduled_posts)
        }
    except Exception as e:
        logger.error(f"❌ Get scheduled error: {e}")
        return {"data": [], "total": 0}

# ==================== COMMENTS ====================

@app.get("/comments")
async def get_comments():
    """Get recent comments"""
    try:
        comments = await ig_api.get_comments()
        formatted_comments = [
            {
                "id": c.get("id"),
                "username": c.get("from", {}).get("username", "Unknown"),
                "text": c.get("text", ""),
                "timestamp": c.get("timestamp", ""),
                "status": "pending",
                "reply": None
            }
            for c in comments
        ]
        
        logger.info(f"💬 Retrieved {len(formatted_comments)} comments")
        return formatted_comments
    except Exception as e:
        logger.error(f"❌ Comments error: {e}")
        return []

# ==================== AI ENDPOINTS ====================

def get_claude_client():
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)

@app.post("/ai/caption")
async def generate_caption(request: CaptionRequest):
    """Generate Instagram caption with Claude"""
    try:
        client = get_claude_client()
        
        message = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": f"""Write an engaging Instagram caption for this post:
"{request.prompt}"

Requirements:
- Keep it under 150 characters
- Use conversational tone
- Add relevant emojis
- Make it shareable"""
                }
            ]
        )
        
        caption = message.content[0].text
        logger.info(f"✨ Generated caption (Claude)")
        
        return {
            "caption": caption,
            "model": settings.CLAUDE_MODEL,
            "tokens_used": message.usage.output_tokens
        }
    except Exception as e:
        logger.error(f"❌ Caption generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate caption: {str(e)}")

@app.post("/ai/hashtags")
async def generate_hashtags(request: HashtagsRequest):
    """Generate Instagram hashtags with Claude"""
    try:
        client = get_claude_client()
        
        message = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": f"""Generate 15 relevant Instagram hashtags for this topic:
"{request.topic}"

Return ONLY hashtags as a comma-separated list, no explanations.
Example: productivity, lifestyle, entrepreneur, businessowner"""
                }
            ]
        )
        
        hashtags_text = message.content[0].text
        hashtags = [tag.strip().lstrip("#") for tag in hashtags_text.split(",")]
        
        logger.info(f"✨ Generated {len(hashtags)} hashtags")
        
        return {
            "hashtags": hashtags,
            "count": len(hashtags),
            "model": settings.CLAUDE_MODEL
        }
    except Exception as e:
        logger.error(f"❌ Hashtag generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate hashtags: {str(e)}")

# ==================== WEBSOCKET ====================

@app.websocket("/ws/analytics")
async def websocket_analytics(websocket: WebSocket):
    """Real-time analytics updates via WebSocket"""
    await websocket.accept()
    logger.info("🔌 WebSocket connected")
    
    try:
        while True:
            analytics = await get_analytics()
            await websocket.send_json(analytics)
            await asyncio.sleep(5)
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
    finally:
        logger.info("🔌 WebSocket disconnected")

# ==================== ERROR HANDLER ====================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"❌ Unhandled error: {exc}", exc_info=True)
    return {
        "status": "error",
        "message": str(exc)
    }

# ==================== RUN ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
        )
