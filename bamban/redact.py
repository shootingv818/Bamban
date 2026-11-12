"""Turn a raw HAR into a SHAREABLE endpoint map.

The raw HAR contains live secrets (session cookies, tokens, account numbers,
real balances). This module reads it and produces a map that keeps only the
*structure* we need to build the bot:

  - method + URL with all query values and long digit runs masked
  - response status and content-type
  - the JSON *shape* (field names kept, every value replaced by its type)
  - the JSON request *shape* for write-type calls (values masked too)

Field NAMES are preserved (they are not secret and tell us where the balance /
transactions live). VALUES are never emitted.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_LONG_DIGITS = re.compile(r"\d{5,}")
_MASK = "<redacted>"


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    path = _LONG_DIGITS.sub(_MASK, parts.path)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode([(k, _MASK) for k, _ in pairs])
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def shape(value: Any) -> Any:
    """Recursively replace values with type tokens, keeping dict keys."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return []
        # One representative element shape + the count (counts are not secret).
        return [shape(value[0]), f"... x{len(value)}"] if len(value) > 1 else [shape(value[0])]
    if isinstance(value, bool):  # before int: bool is a subclass of int
        return "bool"
    if isinstance(value, (int, float)):
        return "num"
    if value is None:
        return "null"
    return "str"


def _decode_body(content: dict[str, Any]) -> str | None:
    text = content.get("text")
    if text is None:
        return None
    if content.get("encoding") == "base64":
        try:
            return base64.b64decode(text).decode("utf-8", "replace")
        except Exception:
            return None
    return text


def _shape_json(raw_text: str | None) -> Any:
    if not raw_text:
        return None
    try:
        return shape(json.loads(raw_text))
    except Exception:
        return "<unparseable-json>"


def _host_included(host: str, include_hosts: list[str]) -> bool:
    if not include_hosts:
        return True
    return any(h and h in host for h in include_hosts)


def build_endpoint_map(har_path: str | Path, include_hosts: list[str] | None = None) -> list[dict]:
    """Parse a HAR file and return a de-duplicated, redacted endpoint list."""
    include_hosts = include_hosts or []
    data = json.loads(Path(har_path).read_text(encoding="utf-8"))
    entries = data.get("log", {}).get("entries", []) or []

    out: list[dict] = []
    seen: set[tuple] = set()

    for entry in entries:
        req = entry.get("request", {}) or {}
        res = entry.get("response", {}) or {}
        url = req.get("url", "") or ""
        host = urlsplit(url).netloc
        if not _host_included(host, include_hosts):
            continue

        method = req.get("method", "")
        status = res.get("status", 0)
        red_url = redact_url(url)
        key = (method, red_url, status)
        if key in seen:
            continue
        seen.add(key)

        content = res.get("content", {}) or {}
        resp_mime = (content.get("mimeType") or "").split(";")[0].strip()

        item: dict[str, Any] = {
            "method": method,
            "url": red_url,
            "status": status,
            "response_content_type": resp_mime,
        }
        if "json" in resp_mime:
            item["response_shape"] = _shape_json(_decode_body(content))

        post = req.get("postData", {}) or {}
        post_mime = (post.get("mimeType") or "").split(";")[0].strip()
        if "json" in post_mime:
            item["request_shape"] = _shape_json(post.get("text"))

        out.append(item)

    # Stable ordering: JSON responses first, then by url.
    out.sort(key=lambda e: (0 if "json" in (e["response_content_type"] or "") else 1, e["url"]))
    return out


def json_endpoints(endpoint_map: list[dict]) -> list[dict]:
    return [e for e in endpoint_map if "json" in (e.get("response_content_type") or "")]
