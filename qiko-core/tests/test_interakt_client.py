"""HTTP-level tests for InteraktClient (app.integrations.clients), using httpx.MockTransport per
this module's own stated test strategy (no real network)."""

import json

import httpx
import pytest

from app.integrations.clients import InteraktAuthError, InteraktClient, _split_phone_number


def test_split_phone_number_separates_country_code_and_national_number():
    assert _split_phone_number("+447700900000") == ("+44", "7700900000")


def test_split_phone_number_accepts_a_number_missing_the_leading_plus():
    assert _split_phone_number("447700900000") == ("+44", "7700900000")


def test_split_phone_number_handles_a_three_digit_country_code():
    assert _split_phone_number("+971501234567") == ("+971", "501234567")


def test_default_client_sets_the_basic_auth_header_from_the_api_key():
    """_client() (shared by every integration client) only applies the given headers when it
    builds its own httpx.Client, not when one is injected - so this checks the un-injected path,
    and the request-shape test below checks an injected mock client separately."""
    client = InteraktClient(api_key="test-key")
    assert client._c.headers["Authorization"] == "Basic test-key"
    assert client._c.headers["Content-Type"] == "application/json"


def test_send_template_posts_the_expected_shape():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.read()
        return httpx.Response(200, json={"result": True})

    client = InteraktClient(api_key="test-key", client=httpx.Client(
        base_url="https://api.interakt.ai/v1/public", transport=httpx.MockTransport(handler)))
    result = client.send_template("+447700900000", "booking_confirm", ["Jane", "3 Sep"])

    assert result == {"result": True}
    assert captured["url"] == "https://api.interakt.ai/v1/public/message/"
    body = json.loads(captured["body"])
    assert body == {
        "countryCode": "+44",
        "phoneNumber": "7700900000",
        "type": "Template",
        "template": {"name": "booking_confirm", "languageCode": "en", "bodyValues": ["Jane", "3 Sep"]},
    }


def test_send_template_raises_on_a_non_2xx_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "invalid template"})

    client = InteraktClient(api_key="test-key", client=httpx.Client(
        base_url="https://api.interakt.ai/v1/public", transport=httpx.MockTransport(handler)))
    try:
        client.send_template("+447700900000", "unknown_template", [])
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("expected send_template to raise on a 422")


def test_verify_credentials_posts_the_expected_shape():
    """Confirmed against a real Interakt account (JM2-1026 follow-up): despite the name, Get
    Users is a POST, not a GET, and a filters list is mandatory - Interakt 400s with an
    unrelated-looking error if it's omitted. A GET (this test's own first version) gets a 405,
    which InteraktClient.verify_credentials's raise_for_status() would have raised as an
    unhandled httpx.HTTPStatusError, misreporting every valid key as broken."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.read())
        return httpx.Response(200, json={"result": True, "data": {"customers": []}})

    client = InteraktClient(api_key="test-key", client=httpx.Client(
        base_url="https://api.interakt.ai/v1/public", transport=httpx.MockTransport(handler)))
    client.verify_credentials()

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.interakt.ai/v1/public/apis/users/?offset=0&limit=1"
    assert captured["body"] == {
        "filters": [{"trait": "created_at_utc", "op": "gt", "val": "2099-01-01T00:00:00.000Z"}],
    }


@pytest.mark.parametrize("status", [401, 403])
def test_verify_credentials_raises_interakt_auth_error_on_401_or_403(status):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"result": False, "message": "invalid key"})

    client = InteraktClient(api_key="bad-key", client=httpx.Client(
        base_url="https://api.interakt.ai/v1/public", transport=httpx.MockTransport(handler)))
    with pytest.raises(InteraktAuthError):
        client.verify_credentials()


def test_verify_credentials_raises_http_status_error_on_other_failures():
    """A non-auth failure (e.g. Interakt's own 5xx) is not swallowed as "verified", but is also
    not misreported as an InteraktAuthError - the credentials route's own except clause only
    catches InteraktAuthError, so this still surfaces as a 502 through raise_for_status()."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"result": False, "message": "Error processing the request."})

    client = InteraktClient(api_key="test-key", client=httpx.Client(
        base_url="https://api.interakt.ai/v1/public", transport=httpx.MockTransport(handler)))
    with pytest.raises(httpx.HTTPStatusError):
        client.verify_credentials()
