"""
Test reading comments via Facebook Login (Page Access Token).
Run: python scripts/test_fb_comments.py
Then paste your Facebook User Token when asked.
"""

import httpx
import asyncio


async def main():
    print("=" * 50)
    print("  Comment Reader via Facebook Login")
    print("=" * 50)

    TOKEN = input("\nPaste your Facebook User Token: ").strip()
    MEDIA_ID = "18094673984058053"

    async with httpx.AsyncClient(timeout=20) as c:

        # Step 1: Get Pages + IG accounts
        print("\n--- Step 1: Finding your Facebook Page ---")
        r = await c.get(
            "https://graph.facebook.com/v25.0/me/accounts",
            params={
                "fields": "id,name,access_token,instagram_business_account{id,username}",
                "access_token": TOKEN,
            },
        )

        if r.status_code != 200:
            print(f"ERROR: {r.text}")
            print("\nMake sure you generated a User Token with these permissions:")
            print("  pages_show_list, pages_read_engagement,")
            print("  instagram_basic, instagram_manage_comments")
            return

        pages = r.json().get("data", [])
        if not pages:
            print("No Facebook Pages found!")
            print("Your IG Business account must be linked to a Facebook Page.")
            return

        page = pages[0]
        page_token = page["access_token"]
        page_name = page.get("name", "Unknown")
        ig_account = page.get("instagram_business_account", {})
        ig_id = ig_account.get("id", "Not found")
        ig_username = ig_account.get("username", "Not found")

        print(f"  Page: {page_name}")
        print(f"  IG Account: @{ig_username} (ID: {ig_id})")
        print(f"  Page Token: {page_token[:20]}...{page_token[-10:]}")

        # Step 2: Read comments using Page Token
        print(f"\n--- Step 2: Reading comments on post {MEDIA_ID} ---")
        r2 = await c.get(
            f"https://graph.facebook.com/v25.0/{MEDIA_ID}/comments",
            params={
                "fields": "id,text,timestamp,username",
                "access_token": page_token,
            },
        )

        if r2.status_code == 200:
            comments = r2.json().get("data", [])
            if comments:
                print(f"  SUCCESS! Found {len(comments)} comments:\n")
                for cm in comments:
                    print(f"  @{cm.get('username', '?')}: {cm.get('text', '')}")
                    print(f"    ID: {cm['id']}  Time: {cm.get('timestamp', '?')}\n")

                print("\n--- Use this Page Token in your .env ---")
                print(f"IG_ACCESS_TOKEN={page_token}")
                print(f"IG_USER_ID={ig_id}")
            else:
                print("  Got 200 but no comments in data[]")
                print(f"  Raw: {r2.text[:500]}")
        else:
            print(f"  ERROR {r2.status_code}: {r2.text[:500]}")

        # Step 3: Also try reading via IG endpoint
        print(f"\n--- Step 3: Try IG endpoint with Page Token ---")
        r3 = await c.get(
            f"https://graph.instagram.com/v25.0/{MEDIA_ID}/comments",
            params={
                "fields": "id,text,timestamp",
                "access_token": page_token,
            },
        )
        print(f"  Status: {r3.status_code}")
        print(f"  Data: {r3.text[:500]}")


if __name__ == "__main__":
    asyncio.run(main())