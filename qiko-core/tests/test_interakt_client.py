"""HTTP-level tests for InteraktClient (app.integrations.clients), using httpx.MockTransport per
this module's own stated test strategy (no real network)."""

import json

import httpx

from app.integrations.clients import InteraktClient, _split_phone_number


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
