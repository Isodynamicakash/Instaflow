"""
Quick onboard — registers user in the in-memory store
so webhooks can find the account.
Run: python scripts/quick_onboard.py
"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx

SERVER = "http://localhost:8000"


async def main():
    token = os.getenv("IG_ACCESS_TOKEN")
    ig_id = os.getenv("IG_USER_ID")

    async with httpx.AsyncClient(timeout=120) as c:
        # Register user via onboard endpoint
        print("Onboarding @a2gen_t...")
        r = await c.post(f"{SERVER}/api/onboard", json={
            "access_token": token,
            "ig_user_id": ig_id,
            "ig_username": "a2gen_t",
            "whatsapp_number": "",
            "form_data": {
                "niche": "tech blogs",
                "tone": "friendly and professional",
                "goals": "engagement and growth"
            }
        })

        if r.status_code == 200:
            data = r.json()
            print(f"✅ Onboarded! User ID: {data.get('user_id')}")
            print(f"   Posts analyzed: {data.get('posts_analyzed')}")
            print(f"\n   Report preview:")
            print(data.get("report", "")[:500])
        else:
            print(f"❌ Failed: {r.status_code}")
            print(r.text[:500])

        # Also create a test engagement rule
        print("\n\nCreating comment-to-DM trigger rule (LINK)...")
        r2 = await c.post(f"{SERVER}/api/rules", json={
            "user_id": ig_id,
            "rule_type": "comment_trigger",
            "trigger_keywords": ["LINK", "link", "Link"],
            "comment_reply": "Just sent it to your DMs! 📩",
            "dm_template": "Hey! Here's the link you asked for: https://a2gent.com/offer",
            "dm_payload": {"link": "https://a2gent.com/offer"}
        })
        if r2.status_code == 200:
            print("✅ Rule created!")
        else:
            print(f"Rule creation: {r2.text[:200]}")


if __name__ == "__main__":
    asyncio.run(main())