"""
InstaFlow — Complete Main Server with Advanced Analytics
Webhooks + Dashboard API + Real Analytics + Hashtags + Best Times + Demographics
Run: uvicorn backend.main:app --reload --port 8000
Deploy: Railway
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
from collections import defaultdict

from backend.config import settings
from backend.webhooks.instagram import router as ig_webhook_router

# ==================== LOGGING ====================

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
        """Get user's recent posts with engagement metrics"""
        try:
            url = f"{self.api_base}/{self.user_id}/media"
            params = {
                "fields": "id,caption,timestamp,like_count,comments_count,media_type",
                "access_token": self.access_token,
            }
            response = await self.client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            logger.info(f"✅ Fetched {len(data.get('data', []))} posts from Instagram")
            return data.get("data", [])
        except Exception as e:
            logger.error(f"❌ Failed to get posts: {e}")
            return []

    async def get_comments(self):
        """Get recent comments from user's posts"""
        try:
            posts = await self.get_posts()
            all_comments = []
            
            for post in posts[:5]:  # Check last 5 posts
                url = f"{self.api_base}/{post['id']}/comments"
                params = {
                    "fields": "id,from,text,timestamp",
                    "access_token": self.access_token,
                }
                response = await self.client.get(url, params=params, timeout=10.0)
                if response.status_code == 200:
                    comments = response.json().get("data", [])
                    all_comments.extend(comments)
            
            logger.info(f"✅ Fetched {len(all_comments)} comments from Instagram")
            return all_comments
        except Exception as e:
            logger.error(f"❌ Failed to get comments: {e}")
            return []

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

# Initialize Instagram API
ig_api = InstagramAPI(
    settings.IG_ACCESS_TOKEN,
    settings.IG_USER_ID,
    settings.IG_API_BASE
)

# ==================== LIFESPAN ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("="*70)
    logger.info("🚀 InstaFlow Agent — Server Started")
    logger.info(f"   Environment: {settings.ENV}")
    logger.info(f"   IG User ID: {settings.IG_USER_ID or '(not set)'}")
    logger.info(f"   Claude Model: {settings.CLAUDE_MODEL}")
    logger.info(f"   Endpoints:")
    logger.info(f"      POST /webhook/instagram (Webhooks)")
    logger.info(f"      GET  /analytics (Dashboard)")
    logger.info(f"      GET  /analytics/hashtags (Top hashtags)")
    logger.info(f"      GET  /analytics/best-time (Best hours & days)")
    logger.info(f"      GET  /analytics/demographics (Audience)")
    logger.info(f"      POST /posts/schedule")
    logger.info(f"      GET  /posts/scheduled")
    logger.info(f"      GET  /comments")
    logger.info(f"      POST /ai/caption")
    logger.info(f"      POST /ai/hashtags")
    logger.info(f"      WS   /ws/analytics")
    logger.info("="*70)
    
    yield
    
    # Shutdown
    await ig_api.close()
    logger.info("🛑 InstaFlow Agent — Server Stopped")

# ==================== CREATE APP ====================

app = FastAPI(
    title="InstaFlow Agent",
    description="Real-time Instagram AI engagement agent + Advanced Dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

# ==================== MIDDLEWARE ====================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== WEBHOOKS (EXISTING) ====================

# Include all webhook routes from instagram.py
app.include_router(ig_webhook_router)

# ==================== HEALTH & ROOT ====================

@app.get("/")
async def root():
    """Health check"""
    return {
        "name": "InstaFlow Agent",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.ENV,
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "root": "/",
            "health": "/health",
            "webhook": "/webhook/instagram",
            "dashboard": {
                "analytics": "/analytics",
                "hashtags": "/analytics/hashtags",
                "best_time": "/analytics/best-time",
                "demographics": "/analytics/demographics",
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
    """Health check endpoint"""
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
    """Get real analytics from Instagram API
    Returns posts data with engagement metrics for dashboard charts
    """
    try:
        posts = await ig_api.get_posts()
        
        total_likes = sum(p.get("like_count", 0) for p in posts)
        total_comments = sum(p.get("comments_count", 0) for p in posts)
        
        # Format posts data for charts (THIS IS THE FIX!)
        posts_data = [
            {
                "id": p.get("id"),
                "caption": (p.get("caption", "").split("\n")[0][:30] if p.get("caption") else "No caption")[:30],
                "likes": p.get("like_count", 0),
                "comments": p.get("comments_count", 0),
                "timestamp": p.get("timestamp", "")
            }
            for p in posts
        ]
        
        logger.info(f"📊 Analytics: {len(posts)} posts, {total_likes} likes, {total_comments} comments")
        
        return {
            "totalPosts": len(posts),
            "totalLikes": total_likes,
            "totalComments": total_comments,
            "recentEngagement": posts_data  # Real post data for charts!
        }
    except Exception as e:
        logger.error(f"❌ Analytics error: {e}")
        return {
            "totalPosts": 0,
            "totalLikes": 0,
            "totalComments": 0,
            "recentEngagement": []
        }

# ==================== TOP PERFORMING HASHTAGS ====================

@app.get("/analytics/hashtags")
async def get_top_hashtags():
    """Get top performing hashtags from your captions"""
    try:
        posts = await ig_api.get_posts()
        hashtag_performance = {}
        
        for post in posts:
            caption = post.get("caption", "")
            hashtags = [tag.strip() for tag in caption.split() if tag.startswith("#")]
            
            for hashtag in hashtags:
                if hashtag not in hashtag_performance:
                    hashtag_performance[hashtag] = {
                        "count": 0,
                        "total_likes": 0,
                        "total_comments": 0,
                        "avg_engagement": 0
                    }
                
                hashtag_performance[hashtag]["count"] += 1
                hashtag_performance[hashtag]["total_likes"] += post.get("like_count", 0)
                hashtag_performance[hashtag]["total_comments"] += post.get("comments_count", 0)
        
        # Calculate averages and sort
        for tag in hashtag_performance:
            count = hashtag_performance[tag]["count"]
            hashtag_performance[tag]["avg_engagement"] = (
                (hashtag_performance[tag]["total_likes"] + hashtag_performance[tag]["total_comments"]) / count
            ) if count > 0 else 0
        
        # Sort by engagement
        top_hashtags = sorted(
            hashtag_performance.items(),
            key=lambda x: x[1]["avg_engagement"],
            reverse=True
        )[:10]
        
        logger.info(f"🏆 Found {len(hashtag_performance)} unique hashtags")
        
        return {
            "hashtags": [
                {
                    "tag": tag,
                    "count": data["count"],
                    "total_likes": data["total_likes"],
                    "total_comments": data["total_comments"],
                    "avg_engagement": round(data["avg_engagement"], 1)
                }
                for tag, data in top_hashtags
            ],
            "total_unique": len(hashtag_performance)
        }
    except Exception as e:
        logger.error(f"❌ Hashtags error: {e}")
        return {"hashtags": [], "total_unique": 0}

# ==================== BEST TIME TO PUBLISH ====================

@app.get("/analytics/best-time")
async def get_best_publishing_time():
    """Get best times to publish based on engagement"""
    try:
        posts = await ig_api.get_posts()
        
        time_performance = defaultdict(lambda: {"count": 0, "total_engagement": 0})
        day_performance = defaultdict(lambda: {"count": 0, "total_engagement": 0})
        
        for post in posts:
            timestamp = post.get("timestamp", "")
            if not timestamp:
                continue
            
            # Parse timestamp: 2026-06-17T14:49:19+0000
            try:
                post_time = datetime.fromisoformat(timestamp.replace("+0000", "+00:00"))
                hour = post_time.hour
                day = post_time.strftime("%A")
                
                engagement = post.get("like_count", 0) + post.get("comments_count", 0)
                
                time_performance[hour]["count"] += 1
                time_performance[hour]["total_engagement"] += engagement
                
                day_performance[day]["count"] += 1
                day_performance[day]["total_engagement"] += engagement
            except:
                continue
        
        # Calculate averages
        best_hours = []
        for hour in sorted(time_performance.keys()):
            data = time_performance[hour]
            avg_engagement = data["total_engagement"] / data["count"] if data["count"] > 0 else 0
            best_hours.append({
                "hour": f"{hour:02d}:00",
                "engagement": round(avg_engagement, 1),
                "posts": data["count"]
            })
        
        best_days = []
        days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in days_order:
            if day in day_performance:
                data = day_performance[day]
                avg_engagement = data["total_engagement"] / data["count"] if data["count"] > 0 else 0
                best_days.append({
                    "day": day,
                    "engagement": round(avg_engagement, 1),
                    "posts": data["count"]
                })
        
        # Get top 3
        top_hours = sorted(best_hours, key=lambda x: x["engagement"], reverse=True)[:3]
        top_days = sorted(best_days, key=lambda x: x["engagement"], reverse=True)[:3]
        
        logger.info(f"⏰ Best publishing times analyzed")
        
        return {
            "best_hours": top_hours,
            "best_days": top_days,
            "all_hours": best_hours,
            "all_days": best_days
        }
    except Exception as e:
        logger.error(f"❌ Best time error: {e}")
        return {"best_hours": [], "best_days": [], "all_hours": [], "all_days": []}

# ==================== AUDIENCE DEMOGRAPHICS ====================

@app.get("/analytics/demographics")
async def get_user_demographics():
    """Get follower demographics (requires business account)"""
    try:
        # Get business account info
        url = f"{settings.IG_API_BASE}/{settings.IG_USER_ID}"
        params = {
            "fields": "id,username,name,followers_count,follows_count,biography,website,profile_picture_url",
            "access_token": settings.IG_ACCESS_TOKEN,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            account_data = response.json()
        
        logger.info(f"📱 Retrieved account demographics")
        
        return {
            "account": {
                "username": account_data.get("username"),
                "name": account_data.get("name"),
                "followers": account_data.get("followers_count", 0),
                "following": account_data.get("follows_count", 0),
                "biography": account_data.get("biography", ""),
                "website": account_data.get("website", "")
            },
            "insights": {
                "follower_growth_potential": "Analyze followers over time",
                "engagement_rate": "Track from posts data",
                "audience_quality": "High engagement posts suggest quality audience"
            },
            "note": "For detailed demographics, upgrade to Instagram Business Account and use Instagram Insights API"
        }
    except Exception as e:
        logger.error(f"❌ Demographics error: {e}")
        return {
            "account": {},
            "insights": {},
            "note": f"Error: {str(e)}"
        }

# ==================== SCHEDULING ====================

# In-memory storage (use Supabase for production)
scheduled_posts = []

@app.post("/posts/schedule")
async def schedule_post(post: SchedulePostRequest):
    """Schedule a post for later"""
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
    """Get recent comments from Instagram"""
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
    """Create Claude client"""
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)

@app.post("/ai/caption")
async def generate_caption(request: CaptionRequest):
    """Generate Instagram caption with Claude"""
    try:
        if not settings.ANTHROPIC_API_KEY:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
        
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
        if not settings.ANTHROPIC_API_KEY:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
        
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
        hashtags = [tag.strip().lstrip("#") for tag in hashtags_text.split(",") if tag.strip()]
        
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
    """Real-time analytics updates via WebSocket
    Sends analytics every 5 seconds
    """
    await websocket.accept()
    logger.info("🔌 WebSocket connected")
    
    try:
        while True:
            # Get current analytics
            analytics = await get_analytics()
            
            # Send to client
            await websocket.send_json(analytics)
            
            # Wait 5 seconds before next update
            await asyncio.sleep(5)
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
    finally:
        logger.info("🔌 WebSocket disconnected")

# ==================== ERROR HANDLERS ====================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"❌ Unhandled error: {exc}", exc_info=True)
    return {
        "status": "error",
        "message": str(exc),
        "type": type(exc).__name__
    }

# ==================== RUN ====================

if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.getenv("PORT", 8000))
    
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=settings.DEBUG
    )
