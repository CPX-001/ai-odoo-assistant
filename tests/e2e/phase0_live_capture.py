#!/usr/bin/env python3
"""Capture one live embedded Assistant Phase 0 scenario through Odoo HTTP.

Credentials, message text and screen context are inputs only. The written trace deliberately
excludes them, along with assistant answers, plan payloads and raw capability/provider content.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

TERMINAL_TURN_STATES = {
    "awaiting_confirmation",
    "completed",
    "failed",
    "cancelled",
    "recovery_required",
}
PUBLIC_ACTIVITY_TYPES = {
    "queued",
    "started",
    "reasoning.started",
    "tool.started",
    "tool.preview.started",
    "approval.required",
    "approval.approved",
    "execution.barrier",
    "tool.verify.started",
    "reasoning.completed",
}
DIAGNOSTIC_EVENT_TYPE = "diagnostic.timing"
SCREEN_KEYS = {
    "action_id",
    "allowed_context_subset",
    "captured_at",
    "menu_id",
    "model",
    "res_id",
    "selected_ids",
    "view_type",
}


class CaptureError(RuntimeError):
    pass


class OdooJsonClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 15.0) -> None:
        self.base_url = _validated_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        jar = http.cookiejar.CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(jar))

    def authenticate(self, *, db: str, login: str, password: str) -> int:
        result = self.call(
            "/web/session/authenticate",
            {"db": db, "login": login, "password": password},
        )
        uid = result.get("uid") if isinstance(result, dict) else None
        if type(uid) is not int or uid <= 0:
            raise CaptureError("authentication_failed")
        return uid

    def call(self, path: str, params: dict[str, Any]) -> Any:
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "call",
                "params": params,
                "id": uuid.uuid4().hex,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            urljoin(f"{self.base_url}/", path.lstrip("/")),
            data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, UnicodeError, ValueError):
            raise CaptureError("odoo_http_unavailable") from None
        if not isinstance(payload, dict) or payload.get("error") is not None:
            raise CaptureError("odoo_rpc_error")
        if "result" not in payload:
            raise CaptureError("odoo_rpc_error")
        return payload["result"]


def _validated_base_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureError("base_url_invalid")
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CaptureError("base_url_invalid")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise CaptureError("base_url_invalid")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise CaptureError("insecure_remote_http_forbidden")
    return value.strip().rstrip("/")


def _screen_input(value: str | None) -> dict[str, Any]:
    """Build one fresh, bounded browser-context hint for a live capture."""

    supplied: dict[str, Any] = {}
    if value:
        try:
            parsed = json.loads(value)
        except ValueError:
            raise CaptureError("screen_invalid") from None
        if not isinstance(parsed, dict) or set(parsed) - SCREEN_KEYS:
            raise CaptureError("screen_invalid")
        supplied = parsed
    screen: dict[str, Any] = {
        "action_id": None,
        "allowed_context_subset": {},
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "menu_id": None,
        "model": None,
        "res_id": None,
        "selected_ids": [],
        "view_type": None,
    }
    screen.update(supplied)
    # A saved fixture may contain a stale captured_at value. The runner is the capture boundary, so
    # stamp the moment at which this context is actually submitted.
    screen["captured_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return screen


def _catalog(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format_version") != 2:
        raise CaptureError("scenario_catalog_invalid")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        raise CaptureError("scenario_catalog_invalid")
    by_id: dict[str, dict[str, Any]] = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise CaptureError("scenario_catalog_invalid")
        scenario_id = scenario.get("id")
        if not isinstance(scenario_id, str) or scenario_id in by_id:
            raise CaptureError("scenario_catalog_invalid")
        by_id[scenario_id] = scenario
    return by_id


def _safe_event(event: Any) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    event_type = event.get("type")
    if not isinstance(event_type, str):
        return None
    safe: dict[str, Any] = {"type": event_type}
    for key in ("sequence", "diagnostic_code", "occurred_at"):
        value = event.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            safe[key] = value
        elif value is None and key == "diagnostic_code":
            safe[key] = None
    if event_type == DIAGNOSTIC_EVENT_TYPE:
        payload = event.get("payload")
        if isinstance(payload, dict):
            point = payload.get("point")
            elapsed = payload.get("elapsed_ms")
            if isinstance(point, str) and isinstance(elapsed, (int, float)):
                safe["payload"] = {"point": point, "elapsed_ms": round(float(elapsed), 3)}
    return safe


def _safe_snapshot(status: Any) -> dict[str, Any]:
    if not isinstance(status, dict):
        raise CaptureError("turn_status_invalid")
    safe = {
        "state": status.get("state") if isinstance(status.get("state"), str) else None,
        "error_code": (
            status.get("error_code") if isinstance(status.get("error_code"), str) else None
        ),
        "last_sequence": (
            status.get("last_sequence")
            if type(status.get("last_sequence")) is int and status.get("last_sequence") >= 0
            else None
        ),
        "events": [],
    }
    events = status.get("events")
    if isinstance(events, list):
        safe["events"] = [item for event in events if (item := _safe_event(event)) is not None]
    return safe


def _elapsed_ms(started_at: float, now: float) -> float:
    return round(max(0.0, now - started_at) * 1000, 3)


def _latest_diagnostic_code(snapshots: list[dict[str, Any]]) -> str | None:
    codes = [
        event.get("diagnostic_code")
        for snapshot in snapshots
        for event in snapshot.get("events", [])
        if isinstance(event, dict) and isinstance(event.get("diagnostic_code"), str)
    ]
    return codes[-1] if codes else None


def _has_public_activity(snapshot: dict[str, Any]) -> bool:
    return any(
        isinstance(event, dict) and event.get("type") in PUBLIC_ACTIVITY_TYPES
        for event in snapshot.get("events", [])
    )


def _expectation_met(
    scenario: dict[str, Any],
    *,
    outcome_kind: str,
    final_state: str | None,
    request_error_code: str | None,
) -> bool:
    expected = scenario.get("expected")
    if not isinstance(expected, dict) or expected.get("kind") != outcome_kind:
        return False
    if outcome_kind == "request_error":
        codes = expected.get("error_codes")
        return isinstance(codes, list) and request_error_code in codes
    states = expected.get("states")
    return isinstance(states, list) and final_state in states


def capture_enqueue_scenario(
    *,
    client: Any,
    scenario: dict[str, Any],
    message: str,
    screen: dict[str, Any],
    timeout_seconds: float = 180.0,
    poll_interval_seconds: float = 0.5,
    monotonic: Any = time.monotonic,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    if scenario.get("entrypoint") != "enqueue":
        raise CaptureError("scenario_entrypoint_not_supported")
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        raise CaptureError("message_invalid")
    if not isinstance(screen, dict):
        raise CaptureError("screen_invalid")

    started_at = float(monotonic())
    timings: list[dict[str, Any]] = [{"point": "submit_received", "elapsed_ms": 0.0}]
    snapshots: list[dict[str, Any]] = []
    first_activity = False

    queued = client.call(
        "/odoo_ai/v1/turn",
        {
            "message": message,
            "screen": screen,
            "conversation_id": None,
            "client_request_id": f"phase0-{uuid.uuid4()}",
        },
    )
    now = float(monotonic())
    if not isinstance(queued, dict):
        raise CaptureError("enqueue_response_invalid")

    if queued.get("ok") is not True:
        error = queued.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        if not isinstance(code, str):
            raise CaptureError("enqueue_response_invalid")
        timings.append({"point": "browser_final", "elapsed_ms": _elapsed_ms(started_at, now)})
        return {
            "format_version": 1,
            "capture_kind": "live_http",
            "scenario_id": scenario["id"],
            "timings": timings,
            "status_snapshots": [],
            "request_error_code": code,
            "original_error_code": code,
            "ui_error_code": None,
            "model_turns": None,
            "tool_calls": None,
            "token_usage": None,
            "expectation_met": _expectation_met(
                scenario,
                outcome_kind="request_error",
                final_state=None,
                request_error_code=code,
            ),
        }

    turn_id = queued.get("turn_id")
    if not isinstance(turn_id, str) or not turn_id:
        raise CaptureError("enqueue_response_invalid")
    timings.append(
        {
            "point": "turn_persisted",
            "elapsed_ms": _elapsed_ms(started_at, now),
            "turn_id": turn_id,
        }
    )
    snapshot = _safe_snapshot(queued)
    snapshots.append(snapshot)
    if _has_public_activity(snapshot):
        first_activity = True
        timings.append(
            {
                "point": "browser_first_activity",
                "elapsed_ms": _elapsed_ms(started_at, now),
                "turn_id": turn_id,
            }
        )

    last_sequence = snapshot["last_sequence"] if isinstance(snapshot["last_sequence"], int) else 0
    deadline = started_at + timeout_seconds
    final_status = queued

    while final_status.get("state") not in TERMINAL_TURN_STATES:
        if float(monotonic()) >= deadline:
            raise CaptureError("capture_timeout")
        sleep(poll_interval_seconds)
        status = client.call(
            "/odoo_ai/v1/turn/status",
            {"turn_id": turn_id, "after_sequence": last_sequence},
        )
        if not isinstance(status, dict) or status.get("ok") is not True:
            raise CaptureError("turn_status_invalid")
        if status.get("turn_id") != turn_id:
            raise CaptureError("turn_status_mismatch")
        final_status = status
        snapshot = _safe_snapshot(status)
        snapshots.append(snapshot)
        if not first_activity and _has_public_activity(snapshot):
            first_activity = True
            timings.append(
                {
                    "point": "browser_first_activity",
                    "elapsed_ms": _elapsed_ms(started_at, float(monotonic())),
                    "turn_id": turn_id,
                }
            )
        if isinstance(snapshot["last_sequence"], int):
            last_sequence = snapshot["last_sequence"]
        if status.get("state") in TERMINAL_TURN_STATES:
            break

    finished = float(monotonic())
    timings.append(
        {
            "point": "browser_final",
            "elapsed_ms": _elapsed_ms(started_at, finished),
            "turn_id": turn_id,
            "state": final_status.get("state"),
        }
    )
    final_state = final_status.get("state")
    final_error = (
        final_status.get("error_code")
        if isinstance(final_status.get("error_code"), str)
        else None
    )
    original_error = _latest_diagnostic_code(snapshots) or final_error
    return {
        "format_version": 1,
        "capture_kind": "live_http",
        "scenario_id": scenario["id"],
        "timings": timings,
        "status_snapshots": snapshots,
        "request_error_code": None,
        "original_error_code": original_error,
        "ui_error_code": None,
        "model_turns": None,
        "tool_calls": None,
        "token_usage": None,
        "expectation_met": _expectation_met(
            scenario,
            outcome_kind="turn",
            final_state=final_state if isinstance(final_state, str) else None,
            request_error_code=None,
        ),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ODOO_AI_PHASE0_BASE_URL", "http://127.0.0.1:8069"),
    )
    parser.add_argument("--db", default=os.environ.get("ODOO_AI_PHASE0_DB"))
    parser.add_argument("--login", default=os.environ.get("ODOO_AI_PHASE0_LOGIN"))
    parser.add_argument("--scenario", required=True)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).with_name("embedded_phase0_scenarios.json"),
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--poll-interval-ms", type=int, default=500)
    parser.add_argument("--ui-error-code", default=os.environ.get("ODOO_AI_PHASE0_UI_ERROR_CODE"))
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    password = os.environ.get("ODOO_AI_PHASE0_PASSWORD")
    message = os.environ.get("ODOO_AI_PHASE0_MESSAGE")
    screen_text = os.environ.get("ODOO_AI_PHASE0_SCREEN_JSON")
    if not args.db or not args.login or not password or not message:
        raise SystemExit(
            "Set ODOO_AI_PHASE0_DB, ODOO_AI_PHASE0_LOGIN, ODOO_AI_PHASE0_PASSWORD and "
            "ODOO_AI_PHASE0_MESSAGE. ODOO_AI_PHASE0_SCREEN_JSON is optional."
        )
    try:
        screen = _screen_input(screen_text)
    except CaptureError as error:
        raise SystemExit(f"Invalid ODOO_AI_PHASE0_SCREEN_JSON: {error}") from None

    scenarios = _catalog(args.catalog)
    scenario = scenarios.get(args.scenario)
    if scenario is None:
        raise SystemExit(f"Unknown Phase 0 scenario: {args.scenario}")
    if scenario.get("entrypoint") != "enqueue":
        raise SystemExit(
            f"Scenario {args.scenario} uses entrypoint={scenario.get('entrypoint')!r}; "
            "this capture runner currently supports enqueue scenarios only."
        )

    client = OdooJsonClient(args.base_url)
    client.authenticate(db=args.db, login=args.login, password=password)
    trace = capture_enqueue_scenario(
        client=client,
        scenario=scenario,
        message=message,
        screen=screen,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=max(1, args.poll_interval_ms) / 1000,
    )
    if args.ui_error_code is not None:
        if re.fullmatch(r"[a-z0-9_]{1,128}", args.ui_error_code) is None:
            raise SystemExit("--ui-error-code must be one normalized product error code.")
        trace["ui_error_code"] = args.ui_error_code
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "scenario_id": trace["scenario_id"],
                "capture_kind": trace["capture_kind"],
                "expectation_met": trace["expectation_met"],
                "trace": str(args.out),
            },
            sort_keys=True,
        )
    )
    return 0 if trace["expectation_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
