import pytest

from app.modules.email.sender import ConsoleEmailSender
from app.modules.leads.service import LeadError, LeadService


def test_capture_persists_and_notifies():
    mail = ConsoleEmailSender()
    svc = LeadService(mail, notify_to="sales@qiko.ai")
    lead = svc.capture("enterprise", "Acme Corp", "buyer@acme.com", {"seats": 50})
    assert lead.kind == "enterprise" and lead.email == "buyer@acme.com"
    assert svc.all() == [lead]
    assert mail.sent[0]["to"] == "sales@qiko.ai" and "Acme Corp" in mail.sent[0]["subject"]


def test_validation():
    svc = LeadService(ConsoleEmailSender())
    with pytest.raises(LeadError):
        svc.capture("spam", "x", "a@b.com")          # unknown kind
    with pytest.raises(LeadError):
        svc.capture("rag_wired", "", "a@b.com")       # missing name
    with pytest.raises(LeadError):
        svc.capture("rag_wired", "x", "not-an-email")  # invalid email
