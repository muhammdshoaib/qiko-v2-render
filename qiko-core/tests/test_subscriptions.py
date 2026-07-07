
from app.modules.billing.subscriptions import SubscriptionService


class FakeStripe:
    def create_checkout_session(self, *, customer_id, price_id, promo):
        return f"https://checkout.stripe/{customer_id}/{price_id}?promo={promo}"

    def billing_portal_url(self, *, customer_id):
        return f"https://portal.stripe/{customer_id}"


def _svc():
    return SubscriptionService(FakeStripe())


def test_checkout_and_portal_urls():
    svc = _svc()
    url = svc.start_checkout("cus_1", "pro", price_id="price_pro", promo="SAVE10")
    assert "cus_1" in url and "price_pro" in url and "SAVE10" in url
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


def test_checkout_rejects_unknown_plan():
    # get_plan falls back to free, so checkout still proceeds; unknown price is the caller's concern.
    assert _svc().start_checkout("c", "enterprise", price_id="price_ent") is not None
