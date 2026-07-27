import httpx
import pytest

from app.modules.channels.slack_oauth import (
    InstallationStore,
    SlackInstallation,
    SlackOAuth,
    SlackOAuthError,
    WorkspaceLinkStore,
)


def test_install_url_has_client_scope_state():
    url = SlackOAuth(InstallationStore()).install_url("st8")
    assert url.startswith("https://slack.com/oauth/v2/authorize?")
    assert "scope=chat" in url and "state=st8" in url


def test_installation_store_save_fetch_delete():
    store = InstallationStore()
    store.save(SlackInstallation(team_id="T1", bot_token="xoxb-1", bot_user_id="B1"))
    assert store.fetch("T1").bot_token == "xoxb-1"
    store.delete("T1")
    assert store.fetch("T1") is None


def test_workspace_link_resolves_worker():
    links = WorkspaceLinkStore()
    links.link("acme", "T1", "U1", "worker-9")
    assert links.resolve("acme", "T1", "U1") == "worker-9"
    assert links.resolve("acme", "T1", "U2") is None
    assert links.resolve("beta", "T1", "U1") is None


def test_exchange_code_saves_installation():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/oauth.v2.access"
        return httpx.Response(200, json={
            "ok": True, "access_token": "xoxb-abc", "bot_user_id": "B9",
            "team": {"id": "T9"}, "authed_user": {"id": "U9"},
        })

    store = InstallationStore()
    oauth = SlackOAuth(store, client=httpx.Client(transport=httpx.MockTransport(handler)))
    inst = oauth.exchange_code("code123")
    assert inst.team_id == "T9" and inst.bot_token == "xoxb-abc" and inst.installed_by == "U9"
    assert store.fetch("T9").bot_user_id == "B9"


def test_exchange_code_error_raises():
    def handler(req):
        return httpx.Response(200, json={"ok": False, "error": "invalid_code"})

    oauth = SlackOAuth(InstallationStore(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(SlackOAuthError):
        oauth.exchange_code("bad")
