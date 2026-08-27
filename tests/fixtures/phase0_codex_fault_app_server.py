#!/usr/bin/env python3
"""Deterministic Codex App Server fault fixture for Phase 0 validation.

The fixture intentionally implements only the minimal account/runtime protocol needed by the
current embedded Odoo path. It never executes tools or echoes request content.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Iterable

INITIALIZE_RESULT = {
    "platformFamily": "linux",
    "platformOs": "linux",
    "userAgent": "odoo-ai-phase0-fault-fixture",
}
ACCOUNT_RESULT = {
    "requiresOpenaiAuth": True,
    "account": {"type": "chatgpt", "email": None, "planType": "phase0"},
}
THREAD_ID = "phase0-thread"
TURN_ID = "phase0-turn"


def _response(request_id, result):
    return {"id": request_id, "result": result}


def _turn_start_result():
    return {"turn": {"id": TURN_ID}, "threadId": THREAD_ID}


def _invalid_output_events() -> tuple[dict[str, object], ...]:
    message = {
        "id": "phase0-message",
        "type": "agentMessage",
        "phase": "final_answer",
        "text": "not-json",
    }
    return (
        {
            "method": "item/completed",
            "params": {"threadId": THREAD_ID, "turnId": TURN_ID, "item": message},
        },
        {
            "method": "turn/completed",
            "params": {
                "threadId": THREAD_ID,
                "turn": {"id": TURN_ID, "status": "completed", "error": None, "items": []},
            },
        },
    )


def handle_request(mode: str, message: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Return fixed protocol frames for one input frame; request content is never reflected."""
    request_id = message.get("id")
    method = message.get("method")
    if method == "initialize":
        params = message.get("params")
        client_info = params.get("clientInfo") if isinstance(params, dict) else None
        client_name = client_info.get("name") if isinstance(client_info, dict) else None
        if mode == "timeout" and client_name == "odoo-ai-assistant":
            return ()
        return (_response(request_id, INITIALIZE_RESULT),)
    if method == "initialized":
        return ()
    if method == "account/read":
        return (_response(request_id, ACCOUNT_RESULT),)
    if method == "account/rateLimits/read":
        return (_response(request_id, {"rateLimitsByLimitId": {}}),)
    if method == "thread/start":
        return (
            _response(
                request_id,
                {
                    "thread": {"id": THREAD_ID, "ephemeral": True},
                    "runtimeWorkspaceRoots": [],
                },
            ),
        )
    if method == "turn/start":
        base = (_response(request_id, _turn_start_result()),)
        if mode == "invalid_output":
            return (*base, *_invalid_output_events())
        return base
    if method == "turn/interrupt":
        return (_response(request_id, {}),)
    return (
        {
            "id": request_id,
            "error": {"code": -32601, "message": "method not implemented by Phase 0 fixture"},
        },
    )


def run(mode: str, lines: Iterable[str]) -> int:
    if mode not in {"eof", "timeout", "invalid_output"}:
        raise SystemExit("invalid Phase 0 fault mode")
    for raw in lines:
        try:
            message = json.loads(raw)
        except ValueError:
            return 2
        if not isinstance(message, dict):
            return 2
        method = message.get("method")
        for frame in handle_request(mode, message):
            sys.stdout.write(json.dumps(frame, separators=(",", ":"), sort_keys=True) + "\n")
            sys.stdout.flush()
        if method == "turn/start" and mode == "eof":
            return 0
        if method == "turn/start" and mode == "timeout":
            for _ in lines:
                pass
            return 0
    return 0


def main(mode: str) -> int:
    if "--version" in sys.argv[1:]:
        print("codex-cli 0.0.0-phase0-fixture")
        return 0
    if "app-server" not in sys.argv[1:]:
        return 2
    return run(mode, sys.stdin)


if __name__ == "__main__":
    raise SystemExit("invoke one of the codex_phase0_* wrappers")
