import time

import pytest

from app.modules.joseph_mews.investor_token import (
    InvestorTokenError,
    create_investor_activity_token,
    decode_investor_activity_token,
)

_SECRET = "test-investor-activity-secret-not-real"


def test_roundtrip_carries_tenant_and_investor_ref():
    token = create_investor_activity_token(tenant="joseph-mews", investor_ref="inv-45", secret=_SECRET)
    claims = decode_investor_activity_token(token, secret=_SECRET)
    assert claims["tenant"] == "joseph-mews"
    assert claims["investor_ref"] == "inv-45"


def test_wrong_secret_rejected():
    token = create_investor_activity_token(tenant="joseph-mews", investor_ref="inv-45", secret=_SECRET)
    with pytest.raises(InvestorTokenError):
        decode_investor_activity_token(token, secret="a-different-secret")


def test_expired_token_rejected():
    token = create_investor_activity_token(
        tenant="joseph-mews", investor_ref="inv-45", secret=_SECRET, ttl_seconds=-1,
    )
    time.sleep(0.01)
    with pytest.raises(InvestorTokenError):
        decode_investor_activity_token(token, secret=_SECRET)


def test_invalid_token_rejected():
    with pytest.raises(InvestorTokenError):
        decode_investor_activity_token("garbage.token.value", secret=_SECRET)


def test_missing_secret_fails_closed_on_create():
    with pytest.raises(InvestorTokenError):
        create_investor_activity_token(tenant="joseph-mews", investor_ref="inv-45", secret="")


def test_missing_secret_fails_closed_on_decode():
    token = create_investor_activity_token(tenant="joseph-mews", investor_ref="inv-45", secret=_SECRET)
    with pytest.raises(InvestorTokenError):
        decode_investor_activity_token(token, secret="")


def test_a_normal_session_access_token_is_rejected():
    """Token-confusion guard: a token minted for a different purpose (even if it happened to be
    signed with the same secret, which it never should be in practice) must not be accepted here
    just because it decodes -- the type claim has to match."""
    from app.modules.identity.tokens import create_access_token

    other = create_access_token("u1", tenant="joseph-mews", secret=_SECRET)
    with pytest.raises(InvestorTokenError):
        decode_investor_activity_token(other, secret=_SECRET)
