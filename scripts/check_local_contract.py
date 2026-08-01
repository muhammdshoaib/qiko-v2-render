#!/usr/bin/env python3
"""Check the local Caddy HTTP contract without contacting external hosts."""
from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys
import time
from dataclasses import dataclass
from http.client import HTTPConnection
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

REQUEST_TIMEOUT_SECONDS = 2.0
REQUEST_ATTEMPTS = 3
RETRYABLE_STARTUP_STATUS_CODES = frozenset({502, 503, 504})
MAX_RESPONSE_BYTES = 1_048_576
LOCAL_IPV4_ADDRESS = "127.0.0.1"
LOCAL_HOSTS = frozenset({"qiko.localhost", "admin.qiko.localhost"})


class ContractFailure(Exception):
    """A sanitized local contract failure."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ContractFailure("arguments: provide one numeric --port value")


@dataclass(frozen=True)
class Check:
    label: str
    hostname: str
    path: str
    response_kind: str = "http"


class LocalIPv4HTTPConnection(HTTPConnection):
    def connect(self) -> None:
        self.sock = socket.create_connection(
            (LOCAL_IPV4_ADDRESS, self.port),
            self.timeout,
            self.source_address,
        )


class LocalIPv4HTTPHandler(HTTPHandler):
    def __init__(self, port: int) -> None:
        super().__init__()
        self._port = port

    def http_open(self, request):
        _assert_local_url(request.full_url, self._port, "transport")
        parsed = urlsplit(request.full_url)
        request.remove_header("Host")
        request.add_unredirected_header("Host", f"{parsed.hostname}:{self._port}")
        return self.do_open(LocalIPv4HTTPConnection, request)


class LocalRedirectHandler(HTTPRedirectHandler):
    def __init__(self, port: int) -> None:
        super().__init__()
        self._port = port

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        _assert_local_url(target, self._port, "redirect")
        return super().redirect_request(req, fp, code, msg, headers, target)


def _parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(description="Check the local Qiko HTTP contract.")
    parser.add_argument("--port", required=True)
    return parser


def _port(raw_port: str) -> int:
    if not raw_port.isascii() or not raw_port.isdigit():
        raise ContractFailure("configuration: --port must be numeric")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise ContractFailure("configuration: --port must be between 1 and 65535")
    return port


def _assert_local_url(url: str, port: int, label: str) -> None:
    try:
        parsed = urlsplit(url)
        parsed_port = parsed.port
    except ValueError as error:
        raise ContractFailure(f"{label}: invalid local URL") from error
    if (
        parsed.scheme != "http"
        or parsed.hostname not in LOCAL_HOSTS
        or parsed_port != port
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ContractFailure(f"{label}: refused a non-local URL")


def _assert_loopback_resolution(hostname: str, port: int, label: str) -> None:
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise ContractFailure(f"{label}: local hostname did not resolve") from error
    if not addresses:
        raise ContractFailure(f"{label}: local hostname did not resolve")
    for address in addresses:
        try:
            if not ipaddress.ip_address(address[4][0]).is_loopback:
                raise ContractFailure(f"{label}: local hostname did not resolve to loopback")
        except ValueError as error:
            raise ContractFailure(f"{label}: local hostname returned an invalid address") from error


def _request(opener, check: Check, port: int) -> bytes:
    label = f"{check.label} {check.path}"
    url = f"http://{check.hostname}:{port}{check.path}"
    _assert_local_url(url, port, label)

    request = Request(url, headers={"User-Agent": "qiko-local-contract/1"})
    for attempt in range(REQUEST_ATTEMPTS):
        try:
            with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                status = response.status
                body = response.read(MAX_RESPONSE_BYTES + 1)
            if not 200 <= status < 300:
                raise ContractFailure(f"{label}: expected HTTP success, received {status}")
            if len(body) > MAX_RESPONSE_BYTES:
                raise ContractFailure(f"{label}: response exceeded the local check limit")
            return body
        except HTTPError as error:
            if (
                error.code in RETRYABLE_STARTUP_STATUS_CODES
                and attempt + 1 < REQUEST_ATTEMPTS
            ):
                time.sleep(0.5)
                continue
            raise ContractFailure(
                f"{label}: expected HTTP success, received {error.code}"
            ) from error
        except ContractFailure:
            raise
        except (TimeoutError, URLError, OSError):
            raise ContractFailure(
                f"{label}: not reachable; verify local services and Caddy"
            ) from None
    raise ContractFailure(f"{label}: local request did not complete")


def _check_json(check: Check, body: bytes) -> None:
    label = f"{check.label} {check.path}"
    try:
        document = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractFailure(f"{label}: response was not valid JSON") from error
    if not isinstance(document, dict):
        raise ContractFailure(f"{label}: expected a JSON object")
    if check.response_kind == "health" and document.get("status") != "ok":
        raise ContractFailure(f"{label}: health status was not ok")
    if check.response_kind == "openapi":
        if not isinstance(document.get("openapi"), str) or not isinstance(
            document.get("paths"), dict
        ):
            raise ContractFailure(f"{label}: response was not an OpenAPI document")


def run(port: int) -> None:
    checks = (
        Check("Creator", "qiko.localhost", "/"),
        Check("Admin", "admin.qiko.localhost", "/"),
        Check("API", "qiko.localhost", "/health", "health"),
        Check("API", "qiko.localhost", "/api/v1/health", "health"),
        Check("API", "qiko.localhost", "/docs"),
        Check("API", "qiko.localhost", "/openapi.json", "openapi"),
    )

    for hostname, label in (
        ("qiko.localhost", "Creator hostname"),
        ("admin.qiko.localhost", "Admin hostname"),
    ):
        _assert_loopback_resolution(hostname, port, label)

    opener = build_opener(
        ProxyHandler({}),
        LocalIPv4HTTPHandler(port),
        LocalRedirectHandler(port),
    )
    for check in checks:
        body = _request(opener, check, port)
        if check.response_kind != "http":
            _check_json(check, body)
        print(f"PASS {check.label} {check.path}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run(_port(args.port))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractFailure as error:
        print(f"FAIL {error}", file=sys.stderr)
        raise SystemExit(1) from None
