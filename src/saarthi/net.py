"""Tiny HTTP helper (stdlib only)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from . import __version__

USER_AGENT = f"Saarthi/{__version__} (desktop companion app)"


def get_json(
    url: str, params: dict | None = None, headers: dict | None = None, body: dict | None = None, timeout: float = 15
):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https URLs built in code)
        return json.loads(resp.read().decode("utf-8"))
