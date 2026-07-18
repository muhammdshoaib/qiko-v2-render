"""Encryption-at-rest: dedicated key with legacy-ciphertext fallback (see app.core.crypto)."""
from app.core import config
from app.core.crypto import decrypt, encrypt


def test_round_trip_with_dedicated_encryption_key(monkeypatch):
    # A dedicated ENCRYPTION_KEY (separate from session_secret) round-trips cleanly, and the
    # ciphertext is not the plaintext at rest.
    monkeypatch.setattr(config.get_settings(), "encryption_key", "a-dedicated-strong-key")
    secret = "vapi_live_abc123"
    token = encrypt(secret)
    assert token != secret
    assert decrypt(token) == secret


def test_legacy_ciphertext_still_decrypts_after_adopting_dedicated_key(monkeypatch):
    # Ciphertext written BEFORE the dedicated key existed (encrypted under the session_secret-derived
    # key) must keep decrypting once ENCRYPTION_KEY is introduced -- no stored secret gets bricked.
    settings = config.get_settings()
    monkeypatch.setattr(settings, "encryption_key", "")  # legacy: key derived from session_secret
    legacy_ct = encrypt("salesforce_refresh_token")

    monkeypatch.setattr(settings, "encryption_key", "a-dedicated-strong-key")  # adopt dedicated key
    assert decrypt(legacy_ct) == "salesforce_refresh_token"  # legacy ciphertext still decrypts

    # And new writes now use the dedicated key while remaining decryptable.
    new_ct = encrypt("new-secret")
    assert new_ct != legacy_ct
    assert decrypt(new_ct) == "new-secret"
