"""Recording credential changes without recording credentials.

Eleven endpoints write or destroy an encrypted integration secret and none of them recorded anything.
They all have the same shape, so the recording is a helper rather than eleven hand-written call sites:
the discipline here is exactly the kind that gets forgotten at the tenth copy, and forgetting it means
writing a customer's Salesforce secret into a table an operator can read.

What gets recorded is the provider, the config key that changed, and a fingerprint. Never a value,
never a prefix of a value, never the ciphertext (which is still a secret in the sense that matters:
it decrypts with a key we hold).

The fingerprint is the point of the whole exercise. A bare "the Slack token changed" cannot answer the
question an incident actually raises, which is whether the value was genuinely rotated or merely saved
again unchanged, and whether it was later rotated BACK to something used before.
"""
from __future__ import annotations

from app.modules.audit import registry
from app.modules.audit import service as audit

# Which config keys belong to which provider, and which of them is the secret. Declared once so a new
# integration cannot be added with its secret quietly outside the set: the credential test below walks
# this table against the router.
PROVIDERS: dict[str, str] = {
    "vapi": "vapi_api_key_encrypted",
    "salesforce": "salesforce_client_secret_encrypted",
    "calendly": "calendly_token_encrypted",
    "clickup": "clickup_api_token_encrypted",
    "slack": "slack_bot_token_encrypted",
    "gmail": "gmail_app_password_encrypted",
    "teams": "webhook_url_encrypted",
}


def _actor(claims: dict) -> tuple[str, str]:
    email = str(claims.get("email") or claims.get("sub") or "")
    return email, email


def credential_audit(*, action: str, provider: str, tenant: str, agent_id: str,
                     agent_name: str | None, claims: dict, secret: str | None,
                     decrypt_previous, request=None):
    """Build the callback that AgentStore.update_config invokes inside its transaction.

    A callback rather than a prepared row, because the previous config has to be read under the row
    lock. An earlier version read the agent first and passed the old value in, which was wrong twice
    over: the in-memory store returns a live object that the update then mutated, so every audit
    reported no change, and even against SQL there was a window in which another writer could land
    between the read and the update.

    `secret` is the PLAINTEXT, taken before encryption, and only its fingerprint leaves this function.
    Fingerprinting the ciphertext would not work: two encryptions of one value differ, so every
    re-save of an unchanged form would look like a rotation, which is exactly the distinction the
    fingerprint exists to make.
    """
    actor_id, actor_label = _actor(claims)

    def build(previous_config: dict) -> dict:
        previous_secret = decrypt_previous(previous_config)
        metadata = {
            "fingerprint_before": audit.fingerprint_of(previous_secret),
            "fingerprint_after": audit.fingerprint_of(secret),
        }
        if action == registry.CREDENTIAL_SET:
            # A real rotation versus a re-save of the same value is the difference between "the leaked
            # key is dead" and "the leaked key is still live".
            metadata["rotated"] = bool(secret) and secret != previous_secret
        return audit.build_row(audit.AuditEvent(
            action=action, target_id=agent_id, target_label=agent_name, tenant_id=tenant,
            actor_type=audit.USER, actor_id=actor_id, actor_label=actor_label,
            changes={"provider": provider, "key": PROVIDERS.get(provider, "unknown")},
            metadata=metadata), request=request)

    return build


async def record_credential_tested(store, *, provider: str, tenant: str, agent_id: str,
                                   agent_name: str | None, claims: dict, ok: bool,
                                   request=None) -> None:
    """A credential was decrypted and used against the third party.

    Not a state change, so it would ordinarily be below the audit line. It is here because it is the
    cheapest available signal that a leaked encryption key is being exercised: a burst of credential
    tests across tenants looks like nothing in application logs and unmistakable here.
    """
    actor_id, actor_label = _actor(claims)
    await audit.record(store, audit.AuditEvent(
        action=registry.CREDENTIAL_TESTED, target_id=agent_id, target_label=agent_name,
        tenant_id=tenant, actor_type=audit.USER, actor_id=actor_id, actor_label=actor_label,
        outcome=audit.SUCCESS if ok else audit.FAILURE,
        changes={"provider": provider, "result": "ok" if ok else "failed"}), request=request)
