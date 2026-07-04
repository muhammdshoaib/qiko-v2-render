from app.modules.channels.whatsapp import WhatsAppAdapter, verify_webhook


def test_webhook_verify_strict():
    assert verify_webhook("subscribe", "good", "CHAL", expected_token="good") == "CHAL"
    assert verify_webhook("subscribe", "bad", "CHAL", expected_token="good") is None
    assert verify_webhook("subscribe", "good", "CHAL", expected_token="") is None  # no token configured


def _payload(mid: str, text: str) -> dict:
    return {"entry": [{"changes": [{"value": {"messages": [
        {"id": mid, "from": "15551234", "type": "text", "text": {"body": text}}]}}]}]}


class FakeWA:
    def __init__(self):
        self.sent = []

    def send_text(self, to, text):
        self.sent.append((to, text))
        return {"ok": True}


def test_inbound_dedup_and_extraction():
    adapter = WhatsAppAdapter(FakeWA())
    msgs = adapter.handle_inbound(_payload("wamid.1", "hello"))
    assert len(msgs) == 1 and msgs[0].text == "hello" and msgs[0].from_number == "15551234"
    # duplicate delivery of the same message id is dropped
    assert adapter.handle_inbound(_payload("wamid.1", "hello")) == []


def test_outbound_reply():
    wa = FakeWA()
    WhatsAppAdapter(wa).reply("15551234", "hi there")
    assert wa.sent == [("15551234", "hi there")]
