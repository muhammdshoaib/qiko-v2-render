import time

import pyotp
import pytest

from app.modules.identity import csrf, twofa
from app.modules.identity.rbac import Role, role_allows
from app.modules.identity.security import hash_password, verify_password
from app.modules.identity.tokens import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)


# --- security ---
def test_password_hash_roundtrip():
    h = hash_password("s3cret!")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("s3cret!", h)
    assert not verify_password("wrong", h)


def test_password_empty_raises():
    with pytest.raises(ValueError):
        hash_password("")


def test_verify_bad_encoded_is_false():
    assert verify_password("x", "not-a-valid-hash") is False
    assert verify_password("x", "md5$1$aa$bb") is False


# --- tokens ---
def test_access_and_refresh_roundtrip():
    a = create_access_token("u1", tenant="acme", role="admin", sid="s1")
    claims = decode_token(a, expected_type="access")
    assert claims["sub"] == "u1" and claims["tenant"] == "acme" and claims["role"] == "admin"
    r = create_refresh_token("u1", sid="s1")
    assert decode_token(r, expected_type="refresh")["sid"] == "s1"


def test_wrong_type_rejected():
    a = create_access_token("u1", sid="s1")
    with pytest.raises(TokenError):
        decode_token(a, expected_type="refresh")


def test_expired_token_rejected():
    a = create_access_token("u1", sid="s1", ttl_seconds=-1)
    time.sleep(0.01)
    with pytest.raises(TokenError):
        decode_token(a)


def test_invalid_token_rejected():
    with pytest.raises(TokenError):
        decode_token("garbage.token.value")


# --- rbac ---
def test_role_hierarchy():
    assert role_allows(Role.owner, Role.viewer)
    assert role_allows(Role.admin, Role.admin)
    assert not role_allows(Role.viewer, Role.admin)
    assert role_allows("editor", "viewer")


# --- csrf ---
def test_csrf_validate():
    t = csrf.generate_csrf_token()
    assert csrf.validate_csrf(t, t)
    assert not csrf.validate_csrf(t, "other")
    assert not csrf.validate_csrf(None, t)
    assert not csrf.validate_csrf(t, None)


# --- twofa ---
def test_totp_verify():
    secret = twofa.new_secret()
    assert "otpauth://" in twofa.provisioning_uri(secret, "user@qiko.ai")
    code = pyotp.TOTP(secret).now()
    assert twofa.verify_totp(secret, code)
    assert not twofa.verify_totp(secret, "000000")
    assert not twofa.verify_totp("", "123456")
