
import pytest

from app.modules.billing.subscriptions import CheckoutUnavailableError, SubscriptionService


class FakeStripe:
    def create_checkout_session(self, *, customer_id, price_id, promo, client_reference_id=None, plan=None):
        return f"https://checkout.stripe/{customer_id}/{price_id}?promo={promo}&plan={plan}"

    def billing_portal_url(self, *, customer_id):
        return f"https://portal.stripe/{customer_id}"


def _svc():
    return SubscriptionService(FakeStripe())


def test_checkout_and_portal_urls():
    svc = _svc()
    # Price is resolved server-side (dev falls back to price_<plan>); the plan is carried for the webhook.
    url = svc.start_checkout("cus_1", "pro", promo="SAVE10")
    assert "cus_1" in url and "price_pro" in url and "SAVE10" in url and "plan=pro" in url
    assert svc.portal_url("cus_1") == "https://portal.stripe/cus_1"


def test_lifecycle_activate_cancel_resume():
    svc = _svc()
    svc.activate("cus_1", "pro")
    assert svc.status("cus_1").status == "active"
    svc.cancel("cus_1")
    assert svc.status("cus_1").cancel_at_period_end is True   # active until period end
    svc.resume("cus_1")
    assert svc.status("cus_1").cancel_at_period_end is False
    assert svc.plan_for("cus_1").worker_limit == 3            # pro (Premium: 3 workers)


def test_plan_defaults_to_free_without_subscription():
    assert _svc().plan_for("unknown").name == "free"


def test_checkout_rejects_non_self_serve_plan():
    # Enterprise is contact-sales (and free is a trial): neither is self-serve checkout.
    with pytest.raises(CheckoutUnavailableError):
        _svc().start_checkout("c", "enterprise")
    with pytest.raises(CheckoutUnavailableError):
        _svc().start_checkout("c", "free")
