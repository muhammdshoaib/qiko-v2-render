import pytest

from app.modules.channels.sessions import ChannelSessionStore


def test_token_stored_encrypted_and_retrievable():
    store = ChannelSessionStore()
    store.set_token("t", "+15551234", "qiko_jwt_secret")
    session = store.get("t", "+15551234")
    assert session.enc_token != "qiko_jwt_secret"          # not plaintext at rest
    assert store.get_token("t", "+15551234") == "qiko_jwt_secret"  # decrypts


def test_worker_selection_and_reply_mode():
    store = ChannelSessionStore()
    store.select_worker("t", "u", "idg")
    store.set_reply_mode("t", "u", "voice")
    s = store.get("t", "u")
    assert s.selected_worker == "idg" and s.reply_mode == "voice"
    with pytest.raises(ValueError):
        store.set_reply_mode("t", "u", "carrier-pigeon")


def test_session_expires_after_ttl():
    store = ChannelSessionStore(ttl_seconds=0)  # expire immediately
    store.select_worker("t", "u", "idg")
    assert store.get("t", "u") is None  # TTL elapsed


def test_sessions_are_tenant_scoped():
    store = ChannelSessionStore()
    store.select_worker("acme", "u", "w")
    assert store.get("beta", "u") is None
