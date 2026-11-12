#!/usr/bin/env python3
"""Standalone redactor for a HAR captured ANYWHERE (phone browser DevTools,
desktop Chrome, etc.) — no Playwright and no YAML needed, pure stdlib.

It turns a raw HAR (which contains live secrets) into the shareable
endpoint_map.json (values masked, field names + types kept).

Run it wherever the HAR is — on the phone in Termux, or on your server:

    python3 redact_har.py path/to/your.har
    python3 redact_har.py your.har -o endpoint_map.json          # custom output
    python3 redact_har.py your.har --hosts bmi.ir,sb24.ir        # keep only these hosts

Then send me ONLY endpoint_map.json. The raw .har stays on your device.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bamban.redact import build_endpoint_map, json_endpoints


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Redact a HAR into a shareable endpoint map")
    ap.add_argument("har", help="path to the .har file to redact")
    ap.add_argument("-o", "--out", default="endpoint_map.json", help="output path")
    ap.add_argument(
        "--hosts",
        default="",
        help="comma-separated host substrings to keep (default: keep all; "
        "the output is redacted either way)",
    )
    args = ap.parse_args(argv)

    har_path = Path(args.har)
    if not har_path.exists():
        print(f"HAR not found: {har_path}", file=sys.stderr)
        return 2

    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    endpoint_map = build_endpoint_map(har_path, include_hosts=hosts)
    Path(args.out).write_text(
        json.dumps(endpoint_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    js = json_endpoints(endpoint_map)
    print(f"\n{len(endpoint_map)} endpoints recorded, {len(js)} return JSON -> {args.out}\n")
    for e in js:
        shp = e.get("response_shape")
        keys = ", ".join(shp.keys()) if isinstance(shp, dict) else str(shp)
        print(f"  [{e['method']} {e['status']}] {e['url']}")
        print(f"       fields: {keys}\n")
    print(f"SAFE to share: {args.out}   |   KEEP PRIVATE: {har_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
