"""Deterministic dev/stub gateways so the full router surface works end-to-end without external
credentials. Real network clients replace these behind the SAME protocols in SCRUM-59."""
from __future__ import annotations


class StubStripeGateway:
    def create_checkout_session(self, *, customer_id: str, price_id: str, promo: str | None = None,
                                client_reference_id: str | None = None, plan: str | None = None) -> str:
        suffix = f"?plan={plan}" if plan else ""
        return f"https://checkout.stripe.test/{customer_id}/{price_id}{suffix}"

    def billing_portal_url(self, *, customer_id: str) -> str:
        return f"https://portal.stripe.test/{customer_id}"

    def create_payment_link(self, *, amount_cents: int, session_id: str, recurring: bool) -> str:
        return f"https://pay.stripe.test/{session_id}?amt={amount_cents}"


class StubCalendlyGateway:
    def available_slots(self, event_type: str) -> list[str]:
        return ["2026-07-10T09:00:00Z", "2026-07-10T10:00:00Z"]

    def create_booking(self, event_type: str, invitee_email: str, start: str) -> dict:
        return {"booked": True, "event_type": event_type, "invitee": invitee_email, "start": start, "stub": True}


class StubGmailGateway:
    def send(self, to: str, subject: str, body: str) -> dict:
        return {"sent": True, "to": to, "subject": subject, "stub": True}


class StubSlackGateway:
    def send_message(self, channel: str, text: str) -> dict:
        return {"ok": True, "channel": channel, "stub": True}


class StubClickUpGateway:
    def create_task(self, list_id: str, name: str, description: str) -> dict:
        return {"id": "task_stub", "list_id": list_id, "name": name, "stub": True}


class StubWhatsAppGateway:
    def send_text(self, to: str, text: str) -> dict:
        return {"to": to, "text": text, "stub": True}


class StubSpeechGateway:
    def transcribe(self, audio: bytes) -> str:
        return audio.decode("utf-8", "ignore") if audio else ""

    def synthesize(self, text: str) -> bytes:
        return b"AUDIO:" + text.encode()


class StubGA4Gateway:
    def run_report(self, start: str, end: str, metrics: list[str], dimensions: list[str]) -> list[dict]:
        return []  # dev: no analytics data until a real GA4 client + creds are configured


class StubSignalEngine:
    def create_project(self, tenant: str, brand: str, domain: str) -> dict:
        return {"project_id": f"proj-{tenant}", "brand": brand, "domain": domain}

    def run_scan(self, project_id: str) -> dict:
        return {"scan_id": f"scan-{project_id}", "project_id": project_id, "status": "queued"}

    def get_score(self, scan_id: str) -> dict:
        return {"scan_id": scan_id, "score": 0}

    def get_buckets(self, scan_id: str) -> dict:
        return {"scan_id": scan_id, "buckets": {}}

    def get_recommendations(self, scan_id: str) -> list[dict]:
        return []

    def export_pdf(self, scan_id: str) -> str:
        return f"exports/{scan_id}.pdf"
