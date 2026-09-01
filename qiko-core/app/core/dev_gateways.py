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

    def create_invoice(self, *, customer_id: str, amount_cents: int, currency: str = "usd",
                       description: str = "", send: bool = False) -> dict:
        return {"id": "in_test", "number": "TEST-1", "amount_due": amount_cents,
                "currency": currency, "status": "open",
                "hosted_invoice_url": f"https://invoice.stripe.test/{customer_id}",
                "invoice_pdf": f"https://invoice.stripe.test/{customer_id}/pdf"}

    def list_invoices(self, *, status: str | None = None,
                      created_after=None) -> list[dict]:
        return []

    def cancel_subscription(self, *, stripe_subscription_id: str) -> None:
        pass

    def resume_subscription(self, *, stripe_subscription_id: str) -> None:
        pass





class StubWhatsAppGateway:
    def send_text(self, to: str, text: str) -> dict:
        return {"to": to, "text": text, "stub": True}


class StubInteraktClient:
    def send_template(self, to: str, template_name: str, params: list[str]) -> dict:
        return {"to": to, "template": template_name, "params": params, "stub": True}


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
