"""The Swagger UI container page (JM2-1134).

Why the page is unauthenticated while the spec it loads is not: a browser cannot attach
X-Api-Key to a navigation, so protecting this URL would mean inventing a second, weaker
credential just to open a page. Instead the page ships empty. It names no path, no schema
and no tag, and it carries no key of its own. The caller pastes the same key they already
use against the API, the page fetches the contract with it, and only then does anything
about the surface appear. A visitor without a key learns that a Joseph Mews worker exists,
which the tenant-scoped URL already told them.

All behaviour lives in docs-assets/docs-shell.js rather than inline here. Security review
found that the application's own SecurityHeadersMiddleware sends "default-src 'self'" with
no script-src, and Caddyfile.dev sets no CSP at all, so an inline script would be blocked in
local development while working on preprod purely because Caddy replaces the header there.

Swagger UI is initialised from an in-memory object rather than a URL because its own spec
fetch cannot carry auth headers. requestInterceptor then puts the same two headers on every
try-it request.
"""
from __future__ import annotations

import html
import json

from app.modules.api_docs.environments import Environment

_LIVE_WARNING = (
    "Live requests write real records against real investors and spend real model budget. "
    "There is no undo."
)


def _server_options(environments: tuple[Environment, ...]) -> str:
    options = []
    for environment in environments:
        url = html.escape(environment.url, quote=True)
        name = html.escape(environment.name)
        if environment.enabled:
            options.append(f'<option value="{url}">{name}</option>')
        else:
            options.append(f'<option value="{url}" disabled>{name} (coming soon)</option>')
    return "\n        ".join(options)


def render(tenant_id: str, environments: tuple[Environment, ...]) -> str:
    """`tenant_id` is only ever a key of TENANT_SPECS: the router rejects anything else
    before calling this. It is escaped anyway, on both the HTML and the JSON path, so that
    property is defence in depth rather than the only thing standing between a future
    caller-supplied value and the page."""
    escaped_id = html.escape(tenant_id)
    # json.dumps does not escape "<", so a value containing "</script>" would close the
    # element it sits in. The config travels in an application/json block rather than a
    # script literal, and the sequence is neutralised regardless.
    config = json.dumps({"tenant": tenant_id}).replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_id} worker API</title>
  <link rel="stylesheet" href="/api/v1/docs-assets/swagger-ui.css">
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; }}
    #gate {{ padding: 24px; max-width: 640px; }}
    #gate h1 {{ font-size: 18px; margin: 0 0 4px; }}
    #gate p {{ color: #555; font-size: 14px; margin: 0 0 16px; }}
    #gate label {{ display: block; font-size: 13px; margin-bottom: 4px; }}
    #gate input, #gate select {{ width: 100%; padding: 8px; font-size: 14px;
      margin-bottom: 12px; box-sizing: border-box; }}
    #gate button {{ padding: 8px 16px; font-size: 14px; cursor: pointer; }}
    #error {{ color: #b00020; font-size: 13px; margin-top: 12px; }}
    #live-warning {{ display: none; background: #fff3cd; border: 1px solid #e0a800;
      padding: 10px; font-size: 13px; margin-bottom: 12px; }}
    #ui {{ display: none; }}
  </style>
</head>
<body>
  <div id="gate">
    <h1>{escaped_id} worker API</h1>
    <p>Generated from the running service, so it cannot describe a version that is not
       deployed. Supply the same API key you use against the API. It is held for this page
       only, is never stored, and is gone when you reload.</p>
    <div id="live-warning">{html.escape(_LIVE_WARNING)}</div>
    <label for="env">Environment</label>
    <select id="env">
        {_server_options(environments)}
    </select>
    <label for="key">API key</label>
    <input id="key" type="password" autocomplete="off" spellcheck="false"
           placeholder="X-Api-Key">
    <button id="load" type="button">Load the contract</button>
    <div id="error"></div>
  </div>
  <div id="ui"></div>

  <script id="docs-config" type="application/json">{config}</script>
  <script src="/api/v1/docs-assets/swagger-ui-bundle.js"></script>
  <script src="/api/v1/docs-assets/docs-shell.js"></script>
</body>
</html>
"""
