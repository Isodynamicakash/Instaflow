"""
Simulate Instagram Webhook — tests the full engagement flow locally.
Sends fake webhook payloads to your running FastAPI server.

Run: python scripts/simulate_webhook.py
(Make sure server is running: uvicorn backend.main:app --reload --port 8000)
"""

import httpx
import asyncio
import json

SERVER_URL = "http://localhost:8000"


async def simulate_comment(sender_username: str, text: str, media_id: str = "18441568843137775"):
    """Simulate an Instagram comment webhook event."""
    payload = {
        "entry": [
            {
                "id": "26173975595576038",  # Your IG user ID
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": f"comment_{int(asyncio.get_event_loop().time())}",
                            "text": text,
                            "from": {
                                "id": "999888777",
                                "username": sender_username,
                            },
                            "media": {
                                "id": media_id,
                            },
                        },
                    }
                ],
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30) as c:
        print(f"\n{'='*50}")
        print(f"Simulating comment from @{sender_username}: \"{text}\"")
        print(f"{'='*50}")

        r = await c.post(f"{SERVER_URL}/webhook/instagram", json=payload)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text}")

        # Wait for background task to process
        await asyncio.sleep(3)
        print("Check your server terminal for the agent's response!")


async def simulate_dm(sender_id: str, text: str):
    """Simulate an Instagram DM webhook event."""
    payload = {
        "entry": [
            {
                "id": "26173975595576038",
                "messaging": [
                    {
                        "sender": {"id": sender_id},
                        "message": {
                            "mid": f"msg_{int(asyncio.get_event_loop().time())}",
                            "text": text,
                        },
                    }
                ],
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30) as c:
        print(f"\n{'='*50}")
        print(f"Simulating DM from {sender_id}: \"{text}\"")
        print(f"{'='*50}")

        r = await c.post(f"{SERVER_URL}/webhook/instagram", json=payload)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text}")

        await asyncio.sleep(3)


async def main():
    print("""
    ╔══════════════════════════════════════╗
    ║  InstaFlow — Webhook Simulator      ║
    ║  Tests the full engagement flow      ║
    ╚══════════════════════════════════════╝
    """)

    # First check if server is running
    async with httpx.AsyncClient() as c:
        try:
            r = await c.get(f"{SERVER_URL}/api/health")
            print(f"Server status: {r.json()}")
        except Exception:
            print("ERROR: Server not running!")
            print("Start it first: uvicorn backend.main:app --reload --port 8000")
            return

    print("\nWhat do you want to simulate?")
    print("1. Comment: 'LINK' (trigger word)")
    print("2. Comment: 'This is amazing!' (genuine praise)")
    print("3. Comment: 'What is the price for bulk?' (serious inquiry)")
    print("4. Comment: 'This is terrible service' (complaint)")
    print("5. Comment: 'Follow me for followers!' (spam)")
    print("6. DM: 'Hi, I want to order'")
    print("7. Custom comment")
    print("8. Run all tests")

    choice = input("\nChoice (1-8): ").strip()

    if choice == "1":
        await simulate_comment("potential_buyer", "LINK")
    elif choice == "2":
        await simulate_comment("happy_follower", "This is amazing! Love your content 🔥")
    elif choice == "3":
        await simulate_comment("business_lead", "What is the price for bulk orders? We need 500 units.")
    elif choice == "4":
        await simulate_comment("unhappy_customer", "This is terrible service, still waiting for my order!")
    elif choice == "5":
        await simulate_comment("spam_bot_99", "Follow me for free followers! Check my bio!")
    elif choice == "6":
        await simulate_dm("888777666", "Hi, I want to place an order for your product")
    elif choice == "7":
        username = input("Sender username: ").strip() or "test_user"
        text = input("Comment text: ").strip() or "Hello!"
        await simulate_comment(username, text)
    elif choice == "8":
        print("\n--- Running all test scenarios ---\n")
        await simulate_comment("buyer_1", "LINK")
        await simulate_comment("fan_1", "Love this! 🔥")
        await simulate_comment("lead_1", "What is the price for 100 units?")
        await simulate_comment("angry_1", "Worst service ever, want my refund!")
        await simulate_comment("spammer", "Follow me!! Free followers!!")
        print("\n--- All tests complete! Check server terminal ---")


if __name__ == "__main__":
    asyncio.run(main())