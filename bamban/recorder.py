"""The capture session itself.

Read-only by design: it navigates to the login page and then hands control to
you. It never fills a form, clicks a button, logs in, or submits anything. You
drive the browser by hand; the tool only records what your genuine session
sends and receives.

Artifacts per run (artifacts/<timestamp>/):
  raw.har            full traffic  — CONTAINS SECRETS, git-ignored, do NOT share
  trace.zip          Playwright trace (replayable) — may contain secrets
  storage_state.json reusable session — CONTAINS SECRETS, git-ignored
  endpoint_map.json  redacted structure — SAFE to share
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from .config import Config
from .redact import build_endpoint_map, json_endpoints

_BANNER = """
============================================================================
  BAMBAN CAPTURE  (read-only — you drive, the tool records)
----------------------------------------------------------------------------
  In the browser window that just opened:
    1. Log in BY HAND  (type your own password and dynamic/OTP yourself).
    2. Open your account and let the balance load.
    3. Open the recent-transactions list and let it load.
    4. (Optional) open the transfer page but DO NOT submit anything.

  The tool is only watching the network — it clicks nothing.

  Artifacts for this run: {run_dir}

  When you are finished, come back here and press ENTER to stop & save.
============================================================================
"""


def _resolve_include_hosts(cfg: Config) -> list[str]:
    configured = cfg.get("capture.include_hosts") or []
    if configured:
        return [str(h) for h in configured]
    # Auto: the base host plus anything under bmi.ir
    return [cfg.base_host, "bmi.ir"]


def _wait_for_user() -> None:
    try:
        input("\n>>> کارها که تمام شد، همین‌جا ENTER بزن تا ضبط ذخیره شود... ")
    except (EOFError, KeyboardInterrupt):
        print()  # newline so the next log line is clean


def run_capture(cfg: Config, log: logging.Logger) -> Path:
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = cfg.path("output.artifacts_dir", "artifacts") / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    har_path = run_dir / "raw.har"
    trace_path = run_dir / "trace.zip"
    storage_path = run_dir / "storage_state.json"
    map_path = run_dir / "endpoint_map.json"

    nav_ms = int(cfg.get("timeouts.navigation_ms", 60000))
    log.info("Starting capture run -> %s", run_dir)
    log.info("Target: %s", cfg.login_url)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=bool(cfg.get("browser.headless", False)),
            slow_mo=int(cfg.get("browser.slow_mo_ms", 0)),
        )
        context = browser.new_context(
            locale=cfg.get("browser.locale", "fa-IR"),
            timezone_id=cfg.get("browser.timezone", "Asia/Tehran"),
            record_har_path=str(har_path),
            record_har_content="embed",
            record_har_mode="full",
        )
        context.tracing.start(screenshots=True, snapshots=True, sources=False)

        page = context.new_page()
        page.set_default_navigation_timeout(nav_ms)
        try:
            page.goto(cfg.login_url, wait_until="domcontentloaded", timeout=nav_ms)
            log.info("Login page opened. Over to you.")
        except PlaywrightError as exc:
            log.error("Could not open %s: %s", cfg.login_url, exc)
            log.error("Check network/VPN and bank.base_url in config.yaml. "
                      "The window is still open — navigate there manually if you can.")

        print(_BANNER.format(run_dir=run_dir))
        _wait_for_user()

        log.info("Stopping capture, saving artifacts ...")
        try:
            context.tracing.stop(path=str(trace_path))
        except PlaywrightError as exc:
            log.error("Could not save trace: %s", exc)
        try:
            context.storage_state(path=str(storage_path))
            log.info("Session saved -> %s (git-ignored, keep private)", storage_path.name)
        except PlaywrightError as exc:
            log.error("Could not save storage_state: %s", exc)

        context.close()  # flushes the HAR to disk
        browser.close()

    if not har_path.exists():
        log.error("No HAR was produced (%s missing). Did the browser open correctly?", har_path)
        return run_dir

    include = _resolve_include_hosts(cfg)
    log.info("Building redacted endpoint map (hosts matching: %s)", ", ".join(include))
    endpoint_map = build_endpoint_map(har_path, include_hosts=include)
    map_path.write_text(json.dumps(endpoint_map, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_summary(endpoint_map, run_dir, map_path, log)
    return run_dir


def _print_summary(endpoint_map: list[dict], run_dir: Path, map_path: Path, log: logging.Logger) -> None:
    js = json_endpoints(endpoint_map)
    print("\n" + "=" * 76)
    print(f"  CAPTURE DONE — {len(endpoint_map)} endpoints recorded, {len(js)} return JSON")
    print("=" * 76)
    if js:
        print("  JSON endpoints (candidates for balance / transactions):\n")
        for e in js:
            top = e.get("response_shape")
            keys = ", ".join(top.keys()) if isinstance(top, dict) else str(top)
            print(f"   [{e['method']} {e['status']}] {e['url']}")
            print(f"        fields: {keys}\n")
    else:
        print("  No JSON endpoints matched. The data may be inline HTML, or the host")
        print("  filter is too narrow — check capture.include_hosts in config.yaml.\n")

    print("  SAFE to share with me:   " + str(map_path))
    print("  KEEP PRIVATE (secrets):  raw.har, trace.zip, storage_state.json")
    print("  All of the above are in: " + str(run_dir))
    print("=" * 76 + "\n")
    log.info("Capture complete. Shareable map: %s", map_path)
