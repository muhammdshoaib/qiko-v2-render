from pathlib import Path

import pytest

from app.core.config import DEFAULT_SESSION_SECRET, Settings


def test_compose_reserves_proxy_ips_and_persists_redis():
    root = Path(__file__).resolve().parents[2]
    base = (root / "docker-compose.yml").read_text()
    preprod = (root / "docker-compose.preprod.yml").read_text()
    live = (root / "docker-compose.live.yml").read_text()
    assert "redis_data:/data" in base and '"--appendonly", "yes"' in base
    assert "ip_range: 172.28.10.128/25" in preprod and "ipv4_address: 172.28.10.2" in preprod
    assert "ip_range: 172.28.20.128/25" in live and "ipv4_address: 172.28.20.2" in live
    assert "proxy_net_v2" in preprod and "proxy_net_v2" in live


def test_release_workflows_require_oidc_sha_and_checksum_provenance():
    root = Path(__file__).resolve().parents[2]
    preprod_workflow = (root / ".github/workflows/deploy-preprod.yml").read_text()
    live_workflow = (root / ".github/workflows/deploy-live.yml").read_text()
    preprod_script = (root / ".github/deploy/redeploy-preprod.sh").read_text()
    live_script = (root / ".github/deploy/redeploy-live.sh").read_text()
    assert "PREPROD_DEPLOY_ROLE_ARN" in preprod_workflow and "aws-access-key-id" not in preprod_workflow
    assert "LIVE_DEPLOY_ROLE_ARN" in live_workflow and "aws-access-key-id" not in live_workflow
    assert "release_sha" in live_workflow and "/qiko/preprod/DEPLOYED_SHA" in live_workflow
    assert "deploy-${{ inputs.release_sha }}.tar.gz" in live_workflow
    assert "deploy-latest.tar.gz" not in live_workflow
    assert "head -n 1 .github/deploy/redeploy-preprod.sh" in preprod_workflow
    assert "head -n 1 .github/deploy/redeploy-live.sh" in live_workflow
    for script in (preprod_script, live_script):
        assert "RELEASE_SHA256" in script and "sha256sum -c" in script and "deploy-$RELEASE_SHA.tar.gz" in script


def test_environment_drives_debug_and_production_gates():
    # Behaviour that matters: only dev exposes debug affordances; only live is production.
    assert Settings(environment="dev").debug is True
    assert Settings(environment="dev").is_production is False
    assert Settings(environment="preprod").debug is False
    assert Settings(environment="live").is_production is True
    assert Settings(environment="live").debug is False


def test_assert_secrets_set_fails_closed_on_default_secret_in_non_dev():
    # dev keeps the forgeable default working (dev/test convenience).
    Settings(environment="dev", session_secret=DEFAULT_SESSION_SECRET).assert_secrets_set()
    # a non-dev deploy must refuse to start on the default -- it could otherwise silently sign and
    # verify tokens with a key anyone can read from source.
    for env in ("preprod", "live"):
        with pytest.raises(RuntimeError, match="SESSION_SECRET"):
            Settings(environment=env, session_secret=DEFAULT_SESSION_SECRET).assert_secrets_set()
    _prod_settings(environment="live").assert_secrets_set()


def _prod_settings(**overrides):
    base = dict(
        session_secret="Ses" + "sion-A1b2C3d4E5f6G7h8I9j0K1l2M3n4",
        encryption_key="Enc" + "rypt-Z9y8X7w6V5u4T3s2R1q0P9o8N7m6",
        use_db_stores=True, task_backend="arq",
        consent_pseudonym_keys={"v1": "Con" + "sent-Q1w2E3r4T5y6U7i8O9p0A1s2D3f4"},
        forwarded_allow_ips="172.28.20.2", email_backend="smtp",
        smtp_host="smtp.example.test", smtp_user="smtp-user", smtp_password="smtp" + "-password-value",
        email_from="sender" + "@" + "example.test")
    base.update(overrides)
    return Settings(**base)


def test_non_dev_rejects_wildcard_and_loopback_only_proxy_trust():
    for value in ("127.0.0.1", "127.0.0.0/8", "127.0.0.1,*", "0.0.0.0/0",
                  "::/0", "0.0.0.0/0,172.28.20.2", "not-an-ip", ""):
        with pytest.raises(RuntimeError, match="FORWARDED_ALLOW_IPS"):
            _prod_settings(environment="live", forwarded_allow_ips=value).assert_secrets_set()


def test_non_dev_rejects_weak_or_reused_secrets():
    for overrides in (
        {"session_secret": "x"},
        {"encryption_key": "replace-with-public-placeholder-value"},
        {"consent_pseudonym_keys": {"v1": "x" * 32}},
        {"encryption_key": "Ses" + "sion-A1b2C3d4E5f6G7h8I9j0K1l2M3n4"},
    ):
        with pytest.raises(RuntimeError):
            _prod_settings(environment="live", **overrides).assert_secrets_set()


def test_non_dev_requires_smtp_email_delivery():
    with pytest.raises(RuntimeError, match="EMAIL_BACKEND=smtp"):
        _prod_settings(environment="preprod", email_backend="console").assert_secrets_set()


def test_non_dev_rejects_incomplete_smtp_configuration():
    for overrides in ({"smtp_host": "localhost"}, {"smtp_user": ""},
                      {"smtp_password": ""}, {"email_from": "REPLACE_WITH_EMAIL_FROM"}):
        with pytest.raises(RuntimeError, match="SMTP"):
            _prod_settings(environment="preprod", **overrides).assert_secrets_set()


def test_assert_secrets_set_requires_prod_safe_stores_and_backend_in_non_dev():
    # dev is unaffected: the in-memory stores + inline backend defaults are fine for dev/tests.
    Settings(environment="dev").assert_secrets_set()

    for env in ("preprod", "live"):
        # in-memory stores would silently drop all data on every restart.
        with pytest.raises(RuntimeError, match="USE_DB_STORES"):
            _prod_settings(environment=env, use_db_stores=False).assert_secrets_set()
        # the inline (eager) backend would run the 30-min generation inline and hit the LB timeout.
        with pytest.raises(RuntimeError, match="TASK_BACKEND"):
            _prod_settings(environment=env, task_backend="eager").assert_secrets_set()
        # a fully prod-safe config boots.
        _prod_settings(environment=env).assert_secrets_set()
