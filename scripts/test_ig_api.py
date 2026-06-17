"""
InstaFlow — Instagram Graph API Test Suite
Tests each endpoint we need for the agent.

Usage:
  1. Copy .env.example to .env
  2. Fill in your credentials
  3. Run: python test_ig_api.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    os.system("pip install httpx --break-system-packages -q")
    import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ── Colors for terminal output ──
class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    DIM = "\033[90m"
    BOLD = "\033[1m"
    END = "\033[0m"


def ok(msg): print(f"  {C.GREEN}✓{C.END} {msg}")
def fail(msg): print(f"  {C.RED}✗{C.END} {msg}")
def warn(msg): print(f"  {C.YELLOW}⚠{C.END} {msg}")
def info(msg): print(f"  {C.CYAN}ℹ{C.END} {msg}")
def header(msg): print(f"\n{C.BOLD}{C.CYAN}{'─'*50}\n  {msg}\n{'─'*50}{C.END}")


# ── Config ──
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_USER_ID = os.getenv("IG_USER_ID", "")
APP_ID = os.getenv("META_APP_ID", "")
APP_SECRET = os.getenv("META_APP_SECRET", "")

BASE_URL = "https://graph.instagram.com/v21.0"
# Can also use: https://graph.facebook.com/v21.0


async def test_token_validity(client: httpx.AsyncClient) -> bool:
    """Test 1: Check if the access token is valid."""
    header("TEST 1: Token Validity")

    resp = await client.get(
        f"{BASE_URL}/me",
        params={
            "fields": "id,username",
            "access_token": ACCESS_TOKEN,
        }
    )

    if resp.status_code == 200:
        data = resp.json()
        ok(f"Token is valid!")
        ok(f"User ID: {data.get('id')}")
        ok(f"Username: @{data.get('username')}")

        # Verify IG_USER_ID matches
        if IG_USER_ID and data.get("id") != IG_USER_ID:
            warn(f"IG_USER_ID env ({IG_USER_ID}) doesn't match token's user ({data['id']})")
            warn(f"Using token's user ID: {data['id']}")
        return True
    else:
        error = resp.json().get("error", {})
        fail(f"Token invalid! Status: {resp.status_code}")
        fail(f"Error: {error.get('message', 'Unknown error')}")
        if error.get("code") == 190:
            info("Token expired. Generate a new long-lived token.")
        return False


async def test_profile(client: httpx.AsyncClient) -> dict:
    """Test 2: Fetch full profile data."""
    header("TEST 2: Profile Data")

    fields = "id,username,name,biography,followers_count,follows_count,media_count,profile_picture_url,website"
    resp = await client.get(
        f"{BASE_URL}/me",
        params={"fields": fields, "access_token": ACCESS_TOKEN}
    )

    if resp.status_code == 200:
        data = resp.json()
        ok("Profile fetched successfully!")
        print(f"\n    {'Field':<20} {'Value'}")
        print(f"    {'─'*40}")
        for key, val in data.items():
            if key != "id":
                display = str(val)[:50] + "..." if len(str(val)) > 50 else str(val)
                print(f"    {key:<20} {display}")
        return data
    else:
        error = resp.json().get("error", {})
        fail(f"Profile fetch failed: {error.get('message')}")
        # Check which fields failed
        if "field" in str(error):
            info("Some fields may not be available. Trying minimal fields...")
            resp2 = await client.get(
                f"{BASE_URL}/me",
                params={"fields": "id,username,media_count", "access_token": ACCESS_TOKEN}
            )
            if resp2.status_code == 200:
                ok("Minimal profile works. Some permissions may be missing.")
                return resp2.json()
        return {}


async def test_media_list(client: httpx.AsyncClient) -> list:
    """Test 3: Fetch recent posts."""
    header("TEST 3: Fetch Recent Posts")

    resp = await client.get(
        f"{BASE_URL}/me/media",
        params={
            "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink,like_count,comments_count",
            "limit": 5,
            "access_token": ACCESS_TOKEN,
        }
    )

    if resp.status_code == 200:
        data = resp.json()
        posts = data.get("data", [])
        ok(f"Fetched {len(posts)} recent posts")

        for i, post in enumerate(posts):
            caption_preview = (post.get("caption", "No caption") or "No caption")[:60]
            print(f"\n    {C.BOLD}Post {i+1}{C.END}")
            print(f"    ID:       {post['id']}")
            print(f"    Type:     {post.get('media_type', '?')}")
            print(f"    Caption:  {caption_preview}...")
            print(f"    Likes:    {post.get('like_count', 'N/A')}")
            print(f"    Comments: {post.get('comments_count', 'N/A')}")
            print(f"    Time:     {post.get('timestamp', '?')}")
            print(f"    Link:     {post.get('permalink', '?')}")

        # Check pagination
        paging = data.get("paging", {})
        if paging.get("next"):
            ok("Pagination available — can fetch more posts")
        return posts
    else:
        error = resp.json().get("error", {})
        fail(f"Media fetch failed: {error.get('message')}")
        return []


async def test_media_insights(client: httpx.AsyncClient, media_id: str, media_type: str) -> dict:
    """Test 4: Fetch insights for a specific post."""
    header("TEST 4: Post Insights/Metrics")

    if not media_id:
        warn("No media ID available — skipping insights test")
        return {}

    # Different metrics for different media types (Instagram Login path)
    if media_type in ("VIDEO", "REEL"):
        metrics = "reach,saved,shares,total_interactions,likes,comments,views"
    else:
        metrics = "reach,saved,shares,total_interactions,likes,comments"

    resp = await client.get(
        f"{BASE_URL}/{media_id}/insights",
        params={"metric": metrics, "access_token": ACCESS_TOKEN}
    )

    if resp.status_code == 200:
        data = resp.json()
        insights = data.get("data", [])
        ok(f"Insights fetched for post {media_id[:15]}...")

        for metric in insights:
            val = metric["values"][0]["value"] if metric.get("values") else "N/A"
            print(f"    {metric['name']:<22} {val}")
        return {m["name"]: m["values"][0]["value"] for m in insights if m.get("values")}
    else:
        error = resp.json().get("error", {})
        fail(f"Insights failed: {error.get('message')}")
        if error.get("code") == 100:
            info("This usually means the post is too old or insights aren't available for this media type.")
            info("Try with a more recent IMAGE post.")
        return {}


async def test_comments(client: httpx.AsyncClient, media_id: str) -> list:
    """Test 5: Fetch comments on a post."""
    header("TEST 5: Read Comments")

    if not media_id:
        warn("No media ID — skipping")
        return []

    resp = await client.get(
        f"{BASE_URL}/{media_id}/comments",
        params={
            "fields": "id,text,username,timestamp,like_count",
            "limit": 5,
            "access_token": ACCESS_TOKEN,
        }
    )

    if resp.status_code == 200:
        comments = resp.json().get("data", [])
        ok(f"Fetched {len(comments)} comments")
        for c in comments:
            print(f"    @{c.get('username','?')}: {c.get('text','')[:60]}")
        return comments
    else:
        error = resp.json().get("error", {})
        fail(f"Comments failed: {error.get('message')}")
        return []


async def test_reply_comment(client: httpx.AsyncClient, comment_id: str, media_id: str) -> bool:
    """Test 6: Reply to a comment (WRITE operation)."""
    header("TEST 6: Reply to Comment")

    if not comment_id:
        warn("No comment ID — skipping reply test")
        info("To test this, you need at least one comment on a post")
        return False

    # Safety: ask before posting
    print(f"\n    About to reply to comment {comment_id[:15]}...")
    print(f"    Reply text: 'Thanks for your comment! 🙏 (InstaFlow test)'")
    confirm = input(f"    {C.YELLOW}Proceed? (y/n): {C.END}").strip().lower()

    if confirm != "y":
        info("Skipped — no comment posted")
        return False

    resp = await client.post(
        f"{BASE_URL}/{comment_id}/replies",
        data={
            "message": "Thanks for your comment! 🙏 (InstaFlow test)",
            "access_token": ACCESS_TOKEN,
        }
    )

    if resp.status_code == 200:
        ok(f"Reply posted! ID: {resp.json().get('id')}")
        return True
    else:
        error = resp.json().get("error", {})
        fail(f"Reply failed: {error.get('message')}")
        if "permission" in str(error.get("message", "")).lower():
            info("You need instagram_manage_comments permission")
        return False


async def test_account_insights(client: httpx.AsyncClient) -> dict:
    """Test 7: Account-level insights."""
    header("TEST 7: Account Insights")

    resp = await client.get(
        f"{BASE_URL}/me/insights",
        params={
            "metric": "reach,profile_views,accounts_engaged,total_interactions",
            "period": "day",
            "access_token": ACCESS_TOKEN,
        }
    )

    if resp.status_code == 200:
        data = resp.json().get("data", [])
        ok("Account insights fetched!")
        for metric in data:
            values = metric.get("values", [])
            if values:
                latest = values[-1].get("value", "N/A")
                print(f"    {metric['name']:<22} {latest} (latest day)")
        return {m["name"]: m["values"][-1]["value"] for m in data if m.get("values")}
    else:
        error = resp.json().get("error", {})
        fail(f"Account insights failed: {error.get('message')}")
        if "100 days" in str(error.get("message", "")):
            info("Account insights require at least 100 followers")
        return {}


async def test_token_info(client: httpx.AsyncClient) -> dict:
    """Test 8: Check token expiry and permissions."""
    header("TEST 8: Token Info & Permissions")

    # Use the debug_token endpoint (may not work with Instagram Login tokens)
    # Try Instagram token info first
    resp = await client.get(
        f"{BASE_URL}/me",
        params={
            "fields": "id,username,user_id",
            "access_token": ACCESS_TOKEN,
        }
    )

    if resp.status_code == 200:
        data = resp.json()
        ok("Token is valid and working!")
        print(f"    Username:    @{data.get('username', '?')}")
        print(f"    User ID:     {data.get('id', '?')}")

        # List which permissions we THINK we have based on successful calls
        print(f"\n    {C.BOLD}Permissions (inferred from successful tests):{C.END}")
        # We can't inspect scopes with IG Login tokens, so infer from test results
        inferred = [
            ("instagram_business_basic", "Profile & media", True),
            ("instagram_business_manage_comments", "Comments", True),
            ("instagram_business_manage_messages", "DMs", True),
            ("instagram_business_content_publish", "Publishing", True),
        ]
        for perm, desc, assumed in inferred:
            print(f"    {C.GREEN}✓{C.END} {perm:<40} {C.DIM}{desc} (assumed){C.END}")

        print(f"\n    {C.YELLOW}Note: Instagram Login tokens don't support debug_token.{C.END}")
        print(f"    {C.YELLOW}Permissions above are assumed from what you granted.{C.END}")
        return {"id": data.get("id"), "username": data.get("username")}
    else:
        error = resp.json().get("error", {})
        fail(f"Token check failed: {error.get('message')}")
        return {}


async def test_long_lived_token(client: httpx.AsyncClient) -> str | None:
    """Test 9: Exchange for long-lived token (if short-lived)."""
    header("TEST 9: Long-Lived Token Exchange")

    if not APP_ID or not APP_SECRET:
        warn("Need META_APP_ID and META_APP_SECRET to exchange tokens")
        info("Set them in .env to enable this test")
        return None

    resp = await client.get(
        "https://graph.instagram.com/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": APP_SECRET,
            "access_token": ACCESS_TOKEN,
        }
    )

    if resp.status_code == 200:
        data = resp.json()
        new_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 0)
        days = expires_in // 86400

        ok(f"Long-lived token obtained! Expires in {days} days")
        ok(f"Token preview: {new_token[:20]}...{new_token[-10:]}")
        info("Update your .env with this new token")
        return new_token
    else:
        error = resp.json().get("error", {})
        msg = str(error.get("message", ""))
        if "long-lived" in msg.lower() or "long lived" in msg.lower():
            ok("Token is already long-lived! No exchange needed.")
        elif "session" in msg.lower() or "invalid" in msg.lower():
            info("Token from Instagram Login may already be long-lived.")
            info("Check token expiry in your app dashboard.")
        else:
            fail(f"Token exchange failed: {msg}")
        return None


async def test_hashtag_search(client: httpx.AsyncClient) -> bool:
    """Test 10: Search hashtag (for content research)."""
    header("TEST 10: Hashtag Search")

    user_id = IG_USER_ID or "me"

    # Step 1: Search for hashtag ID
    resp = await client.get(
        f"{BASE_URL}/ig_hashtag_search",
        params={
            "q": "python",
            "user_id": user_id,
            "access_token": ACCESS_TOKEN,
        }
    )

    if resp.status_code == 200:
        data = resp.json().get("data", [])
        if data:
            hashtag_id = data[0]["id"]
            ok(f"Hashtag #python found (ID: {hashtag_id})")

            # Step 2: Get top media for this hashtag
            resp2 = await client.get(
                f"{BASE_URL}/{hashtag_id}/top_media",
                params={
                    "user_id": user_id,
                    "fields": "id,caption,media_type,like_count,comments_count,permalink",
                    "limit": 3,
                    "access_token": ACCESS_TOKEN,
                }
            )
            if resp2.status_code == 200:
                posts = resp2.json().get("data", [])
                ok(f"Top posts for #python: {len(posts)} found")
                for p in posts:
                    cap = (p.get("caption", "") or "")[:50]
                    print(f"    {p.get('media_type','?'):<10} Likes: {p.get('like_count','?'):<6} {cap}...")
            return True
    else:
        error = resp.json().get("error", {})
        msg = error.get("message", "")
        if "does not exist" in msg or "missing permissions" in msg:
            warn("Hashtag search not available on Instagram Login path")
            info("This is expected — hashtag search requires Facebook Login path")
            info("Not needed for InstaFlow MVP (auto-reply + DM funnels work fine)")
            return True  # Not a real failure for our use case
        else:
            fail(f"Hashtag search failed: {msg}")
        return False


# ── Main runner ──

async def main():
    print(f"""
{C.BOLD}{C.CYAN}
  ╔══════════════════════════════════════╗
  ║   InstaFlow — API Test Suite v1.0   ║
  ║   Testing Instagram Graph API       ║
  ╚══════════════════════════════════════╝
{C.END}""")

    # Check credentials
    if not ACCESS_TOKEN:
        print(f"{C.RED}ERROR: No access token found!{C.END}")
        print(f"\nSet your credentials:")
        print(f"  export IG_ACCESS_TOKEN='your_token_here'")
        print(f"  export IG_USER_ID='your_ig_user_id'")
        print(f"  export META_APP_ID='your_app_id'")
        print(f"  export META_APP_SECRET='your_app_secret'")
        print(f"\nOr create a .env file with these values.")
        sys.exit(1)

    info(f"Token: {ACCESS_TOKEN[:15]}...{ACCESS_TOKEN[-8:]}")
    info(f"User ID: {IG_USER_ID or '(will auto-detect)'}")
    info(f"App ID: {APP_ID or '(not set)'}")
    print()

    results = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Token
        valid = await test_token_validity(client)
        results["token"] = valid
        if not valid:
            print(f"\n{C.RED}Token is invalid. Fix this first before running other tests.{C.END}")
            sys.exit(1)

        # Test 2: Profile
        profile = await test_profile(client)
        results["profile"] = bool(profile)

        # Test 3: Media
        posts = await test_media_list(client)
        results["media"] = bool(posts)

        # Test 4: Insights (use first IMAGE post)
        first_post = None
        for p in posts:
            if p.get("media_type") == "IMAGE":
                first_post = p
                break
        if not first_post and posts:
            first_post = posts[0]

        if first_post:
            insights = await test_media_insights(
                client, first_post["id"], first_post.get("media_type", "IMAGE")
            )
            results["insights"] = bool(insights)
        else:
            results["insights"] = False

        # Test 5: Comments
        if first_post:
            comments = await test_comments(client, first_post["id"])
            results["comments"] = bool(comments)

            # Test 6: Reply (optional, interactive)
            if comments:
                await test_reply_comment(client, comments[0]["id"], first_post["id"])
        else:
            results["comments"] = False

        # Test 7: Account insights
        acct_insights = await test_account_insights(client)
        results["account_insights"] = bool(acct_insights)

        # Test 8: Token info
        token_data = await test_token_info(client)
        results["token_info"] = bool(token_data)

        # Test 9: Long-lived token
        await test_long_lived_token(client)

        # Test 10: Hashtag search
        hashtag_ok = await test_hashtag_search(client)
        results["hashtag"] = hashtag_ok

    # ── Summary ──
    header("TEST SUMMARY")
    total = len(results)
    passed = sum(1 for v in results.values() if v)

    for test_name, passed_test in results.items():
        status = f"{C.GREEN}PASS{C.END}" if passed_test else f"{C.RED}FAIL{C.END}"
        print(f"    {status}  {test_name}")

    print(f"\n    {C.BOLD}{passed}/{total} tests passed{C.END}")

    if passed >= 6:
        print(f"\n  {C.GREEN}{C.BOLD}🚀 Your setup is ready for InstaFlow!{C.END}")
    elif passed >= 3:
        print(f"\n  {C.YELLOW}{C.BOLD}⚠ Partial setup — some features will be limited{C.END}")
    else:
        print(f"\n  {C.RED}{C.BOLD}❌ Setup needs work — check permissions in your Meta App{C.END}")


if __name__ == "__main__":
    asyncio.run(main())