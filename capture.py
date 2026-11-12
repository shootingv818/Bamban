#!/usr/bin/env python3
"""Entry point for the Bamban capture phase.

Usage:
    python capture.py                 # uses config.yaml next to this file
    python capture.py --config x.yaml # custom config

Run this ON YOUR OWN MACHINE/SERVER. It opens a real browser, you log in and
click around by hand, and it records the traffic into artifacts/<timestamp>/.
It never logs in for you and never submits anything.
"""
from __future__ import annotations

import argparse
import sys

from bamban.config import Config, ConfigError
from bamban.logger import get_logger
from bamban.recorder import run_capture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bamban read-only capture tool")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    args = parser.parse_args(argv)

    try:
        cfg = Config.load(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    log = get_logger("bamban.capture", cfg.path("output.logs_dir", "logs"))
    try:
        run_capture(cfg, log)
    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        return 130
    except Exception as exc:  # loud failure, never silent
        log.exception("Capture failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
