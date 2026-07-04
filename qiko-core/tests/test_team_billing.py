from app.modules.billing.subscriptions import SubscriptionService
from app.modules.billing.team_billing import (
    can_team_create_worker,
    resolve_billing_user,
    team_plan,
)


class _FakeStripe:
    def create_checkout_session(self, **kw): return "url"
    def billing_portal_url(self, **kw): return "url"


def _subs_with(active_user: str | None, plan="pro"):
    s = SubscriptionService(_FakeStripe())
    if active_user:
        s.activate(active_user, plan)
    return s


def test_resolve_billing_user_picks_active_member():
    subs = _subs_with("bob")
    assert resolve_billing_user(["alice", "bob", "carol"], subs) == "bob"
    assert resolve_billing_user(["alice", "carol"], subs) is None  # none active


def test_cancelling_member_is_not_billing_user():
    subs = _subs_with("bob")
    subs.cancel("bob")  # cancel_at_period_end
    assert resolve_billing_user(["bob"], subs) is None


def test_team_plan_and_worker_limit():
    subs = _subs_with("bob", "pro")  # limit 5
    members = ["alice", "bob"]
    assert team_plan(members, subs).name == "pro"
    assert can_team_create_worker(members, 4, subs) is True
    assert can_team_create_worker(members, 5, subs) is False   # team-wide limit
    # no active sub -> free (limit 1)
    assert can_team_create_worker(["x"], 1, _subs_with(None)) is False
