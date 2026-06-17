"""
Publish a post to Instagram using InstaFlow's existing API client.
Run from project root: python scripts/publish_post.py
"""

import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from backend.services.instagram_api import InstagramAPI


async def main():
    token = os.getenv("IG_ACCESS_TOKEN")
    ig_id = os.getenv("IG_USER_ID")

    if not token or not ig_id:
        print("Set IG_ACCESS_TOKEN and IG_USER_ID in .env first")
        return

    api = InstagramAPI(token, ig_id)

    # You can change these
    IMAGE_URL = "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=1080"
    CAPTION = (
        "Testing InstaFlow automation 🤖⚡\n\n"
        "This post was published entirely via the Instagram Graph API.\n\n"
        "#instaflow #automation #techblog #api"
    )

    print("Publishing to @a2gen_t...")
    print(f"Image: {IMAGE_URL[:60]}...")
    print(f"Caption: {CAPTION[:60]}...\n")

    try:
        result = await api.publish_photo(IMAGE_URL, CAPTION)
        print(f"✅ Published! Post ID: {result.get('id')}")
        print("Check your Instagram!")
    except Exception as e:
        print(f"❌ Failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())