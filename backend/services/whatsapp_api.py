"""
WhatsApp Business API client — Phase 2 placeholder.
Stubs return success so the rest of the system works without WhatsApp.
"""


class WhatsAppClient:
    def __init__(self, phone_number_id: str = "", access_token: str = ""):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.enabled = bool(phone_number_id and access_token)

    async def send_message(self, to: str, text: str) -> dict:
        if not self.enabled:
            print(f"[WA stub] Would send to {to}: {text[:80]}...")
            return {"status": "stub", "message": "WhatsApp not configured"}
        # Phase 2: real API call
        return {"status": "stub"}

    async def send_approval_request(self, to: str, options: list[dict]) -> dict:
        if not self.enabled:
            print(f"[WA stub] Would send {len(options)} options to {to}")
            return {"status": "stub"}
        return {"status": "stub"}

    async def send_escalation(self, to: str, context: dict) -> dict:
        if not self.enabled:
            print(f"[WA stub] Would escalate to {to}: {context.get('text', '')[:80]}")
            return {"status": "stub"}
        return {"status": "stub"}
