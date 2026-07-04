import pytest

from app.modules.billing.payment_links import PaymentLinkService
from app.modules.email.sender import ConsoleEmailSender


class FakeLinkGateway:
    def create_payment_link(self, *, amount_cents, session_id, recurring):
        return f"https://pay.stripe/{session_id}?amt={amount_cents}&sub={recurring}"


def _svc():
    return PaymentLinkService(FakeLinkGateway(), ConsoleEmailSender())


def test_create_logs_pending_and_emails():
    svc = _svc()
    log = svc.create("cust@x.com", 5000)
    assert log.status == "pending" and log.session_id in log.url
    assert svc.email.sent[0]["to"] == "cust@x.com" and "pay.stripe" in svc.email.sent[0]["body"]


def test_update_status_and_validation():
    svc = _svc()
    log = svc.create("c@x.com", 1000)
    svc.update_status(log.session_id, "paid")
    assert svc.logs_for("c@x.com")[0].status == "paid"
    with pytest.raises(ValueError):
        svc.update_status(log.session_id, "bogus")


def test_mark_as_paid_flips_only_pending():
    svc = _svc()
    svc.create("c@x.com", 1000)
    l2 = svc.create("c@x.com", 2000)
    svc.update_status(l2.session_id, "void")
    changed = svc.mark_as_paid_for_user("c@x.com")
    assert changed == 1  # only the pending one
    statuses = sorted(x.status for x in svc.logs_for("c@x.com"))
    assert statuses == ["paid", "void"]
