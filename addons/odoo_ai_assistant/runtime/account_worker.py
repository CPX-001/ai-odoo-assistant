"""Ephemeral process that owns one Codex device-login App Server session."""

from __future__ import annotations

import argparse
import asyncio
import os
import runpy
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--codex-home", required=True)
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--cancel-path", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--lock-fd", required=True, type=int)
    parser.add_argument("--login-timeout-seconds", required=True, type=int)
    parser.add_argument("--startup-timeout-seconds", required=True, type=float)
    parser.add_argument("--request-timeout-seconds", required=True, type=float)
    parser.add_argument("--shutdown-timeout-seconds", required=True, type=float)
    return parser


def main() -> int:
    args = _parser().parse_args()
    # Load the stdlib-only protocol implementation by its trusted sibling path.
    # This intentionally avoids importing the Odoo addon package: a normal Odoo
    # source checkout may not be importable from a fresh ``sys.executable`` child.
    implementation = runpy.run_path(str(Path(__file__).with_name("account.py")))
    run_device_login_worker = implementation["run_device_login_worker"]

    lock_fd = args.lock_fd
    try:
        os.fstat(lock_fd)
    except OSError:
        return 2
    try:
        asyncio.run(
            run_device_login_worker(
                executable=Path(args.executable),
                codex_home=Path(args.codex_home),
                state_path=Path(args.state_path),
                cancel_path=Path(args.cancel_path),
                attempt_id=args.attempt_id,
                login_timeout_seconds=args.login_timeout_seconds,
                startup_timeout_seconds=args.startup_timeout_seconds,
                request_timeout_seconds=args.request_timeout_seconds,
                shutdown_timeout_seconds=args.shutdown_timeout_seconds,
            )
        )
        return 0
    finally:
        try:
            os.close(lock_fd)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
