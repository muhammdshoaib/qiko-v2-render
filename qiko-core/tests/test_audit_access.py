"""Wave 3 of audit coverage: who can reach a tenant.

The platform-admin side of this has been audited since leg B. The tenant-facing side, which is the
path a customer's own admin actually uses, recorded nothing at all: role changes, member additions and
removals, invitations, and a HARD delete of a login-capable identity.
"""
import asyncio

from app.core.deps import get_user_store
from app.modules.audit import registry
from app.modules.identity.rbac import Role
from app.modules.identity.store import User
from tests.helpers import auth_cookies

ADMIN = auth_cookies("accessco", "admin", user_id="boss", email="boss@accessco.invalid")


def _member(client, user_id: str = "m1", role: Role = Role.editor) -> None:
    asyncio.run(get_user_store().add(User(
        id=user_id, email=f"{user_id}@accessco.invalid", password_hash="x",
        tenant="accessco", role=role, name="A Member")))


def _events(client, action: str | None = None) -> list[dict]:
    rows = client.app.state.audit.rows
    return [r for r in rows if action is None or r["action"] == action]


def test_a_tenant_role_change_is_recorded(client):
    _member(client)
    response = client.put("/api/v1/identity/users/m1/role", cookies=ADMIN, json={"role": "viewer"})
    assert response.status_code == 200

    row = _events(client, registry.TENANT_ROLE_CHANGED)[0]
    assert row["changes"]["role"] == {"from": "editor", "to": "viewer"}
    assert row["actor_label"] == "boss@accessco.invalid"
    assert row["tenant_id"] == "accessco"


def test_the_hard_delete_leaves_a_record_of_the_identity_it_destroyed(client):
    """The largest evidential gap in the platform. This is a hard delete: the row is gone and it
    cascades the user's MFA backup codes. A leaver sample is the first thing an access review asks
    for, and the only record that the user had existed was the row being destroyed."""
    _member(client)
    # The reason travels in the body now, not the query string: a URL is written verbatim into edge
    # access logs, which sit outside the audit store's retention and erasure path.
    response = client.request("DELETE", "/api/v1/identity/users/m1", cookies=ADMIN,
                             json={"reason": "left the company"})
    assert response.status_code == 200
    assert asyncio.run(get_user_store().get_by_id("m1")) is None, "genuinely gone"

    row = _events(client, registry.TENANT_MEMBER_REMOVED)[0]
    # The audit must survive the identity it describes, which is why the table carries no foreign key.
    assert row["target_id"] == "m1"
    assert row["target_label"] == "m1@accessco.invalid", "a removal record that cannot say who answers nothing"
    assert row["event_metadata"]["role"] == "editor"
    assert row["event_metadata"]["hard_delete"] is True
    assert row["reason"] == "left the company"


def test_the_removal_captures_early_and_records_late(client):
    """Both orderings are wrong in different directions, which took a review to see.

    Recording after the delete alone loses the email and role, which are unrecoverable once the row is
    gone. Recording BEFORE the delete, which is what this file originally asserted, lets a failed
    delete leave a row claiming a removal that never happened. The answer is to capture the identifying
    detail first and write the row only once the delete has succeeded.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "modules" / "identity" /
              "users_router.py").read_text()
    body = source[source.index("async def remove_user"):source.index("@router.delete(\"/users/pending")]
    assert body.index("removed_email, removed_role = user.email") < body.index("await store.delete")
    assert body.index("await store.delete") < body.index("audit.record")


def test_the_owner_protections_still_hold_and_produce_no_row(client):
    """A refused mutation is not a change, so it must not leave a row claiming one."""
    _member(client, "own1", Role.owner)
    assert client.put("/api/v1/identity/users/own1/role", cookies=ADMIN,
                      json={"role": "viewer"}).status_code == 400
    assert client.delete("/api/v1/identity/users/own1", cookies=ADMIN).status_code == 400
    assert _events(client, registry.TENANT_ROLE_CHANGED) == []
    assert _events(client, registry.TENANT_MEMBER_REMOVED) == []


def test_an_invitation_is_recorded_before_the_email_is_attempted(client):
    """A send that fails still means a role offer was created against that address."""
    response = client.post("/api/v1/identity/users/invite", cookies=ADMIN,
                           json={"email": "newcomer@acme.invalid", "role": "editor"})
    assert response.status_code in (200, 201)

    row = _events(client, registry.INVITE_SENT)[0]
    assert row["target_id"] == "newcomer@acme.invalid"
    assert row["changes"]["role"] == {"from": None, "to": "editor"}


def test_the_invite_token_is_never_recorded(client):
    """It is a bearer credential that grants access to the tenant."""
    client.post("/api/v1/identity/users/invite", cookies=ADMIN,
                json={"email": "newcomer@acme.invalid", "role": "editor"})
    row = _events(client, registry.INVITE_SENT)[0]
    assert "invite" not in str(row.get("event_metadata", {})).lower()
    assert "eyJ" not in str(row), "no JWT-shaped value anywhere in the row"


def test_team_membership_is_audited_as_a_separate_way_into_the_tenant(client):
    """Team membership is a second, independent path to a tenant's data alongside the identity role.
    An access review that only looked at identity roles would miss every grant made here."""
    _member(client)
    team = client.post("/api/v1/teams", cookies=ADMIN, json={"owner_id": "boss"}).json()
    team_id = team["team_id"]
    client.post(f"/api/v1/teams/{team_id}/members", cookies=ADMIN,
                json={"user_id": "m1", "role": "editor"})
    client.put(f"/api/v1/teams/{team_id}/members/m1", cookies=ADMIN, json={"role": "viewer"})
    client.delete(f"/api/v1/teams/{team_id}/members/m1", cookies=ADMIN)

    added = _events(client, registry.TENANT_MEMBER_ADDED)
    removed = _events(client, registry.TENANT_MEMBER_REMOVED)
    assert added and added[0]["event_metadata"]["via"] == "team"
    assert added[0]["event_metadata"]["team_id"] == team_id
    assert removed and removed[0]["target_id"] == "m1"


def test_access_events_are_readable_without_a_narrow_capability(client):
    """Unlike spend, an access change is context another operator needs before touching the account.
    Only the platform-authority grants sit behind manage_admins."""
    assert registry.spec_for(registry.TENANT_ROLE_CHANGED).read_capability is None
    assert registry.spec_for(registry.TENANT_MEMBER_REMOVED).read_capability is None
    assert registry.spec_for(registry.PLATFORM_ACCESS_GRANTED).read_capability is not None
