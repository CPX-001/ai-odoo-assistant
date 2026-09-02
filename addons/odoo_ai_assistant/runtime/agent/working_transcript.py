"""Bounded private working transcript for durable host-owned agent turns."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TypeAlias

JsonObject: TypeAlias = dict[str, object]
_ALLOWED_KINDS = frozenset(
    {
        "user_input",
        "assistant_decision",
        "task_plan",
        "task_plan_error",
        "capability_call",
        "capability_result",
        "capability_error",
        "plan_step_proposed",
        "plan_prepared",
        "plan_execution_error",
        "verified_effect_receipt",
        "final_answer",
    }
)
_CALL_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
MAX_TRANSCRIPT_BYTES = 128 * 1024
MAX_RESULT_BYTES = 32 * 1024


class WorkingTranscriptError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class WorkingItem:
    sequence: int
    kind: str
    data: JsonObject

    def payload(self) -> JsonObject:
        return {"sequence": self.sequence, "kind": self.kind, "data": dict(self.data)}


def load_working_transcript(value: object) -> tuple[WorkingItem, ...]:
    if value in (None, False, []):
        return ()
    if not isinstance(value, list):
        raise WorkingTranscriptError("agent_working_transcript_invalid")
    items = []
    for position, raw in enumerate(value, 1):
        if (
            not isinstance(raw, dict)
            or set(raw) != {"sequence", "kind", "data"}
            or raw.get("sequence") != position
            or raw.get("kind") not in _ALLOWED_KINDS
            or not isinstance(raw.get("data"), dict)
        ):
            raise WorkingTranscriptError("agent_working_transcript_invalid")
        item = WorkingItem(position, raw["kind"], dict(raw["data"]))
        _validate_item(item)
        items.append(item)
    normalized = tuple(items)
    _validate_call_ids(normalized)
    _bounded(
        [item.payload() for item in normalized],
        MAX_TRANSCRIPT_BYTES,
        "agent_working_transcript_too_large",
    )
    return normalized


def append_working_item(
    items: tuple[WorkingItem, ...], kind: str, data: JsonObject
) -> tuple[WorkingItem, ...]:
    candidate = WorkingItem(len(items) + 1, kind, dict(data))
    _validate_item(candidate)
    combined = (*items, candidate)
    _validate_call_ids(combined)
    _bounded(
        [item.payload() for item in combined],
        MAX_TRANSCRIPT_BYTES,
        "agent_working_transcript_too_large",
    )
    return combined


def transcript_payload(items: tuple[WorkingItem, ...]) -> list[JsonObject]:
    payload = [item.payload() for item in items]
    load_working_transcript(payload)
    return payload


def working_transcript_bytes(items: tuple[WorkingItem, ...]) -> int:
    """Return the canonical serialized size used by the transcript budget."""
    payload = [item.payload() for item in items]
    try:
        return len(
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
    except (TypeError, ValueError):
        raise WorkingTranscriptError("agent_working_transcript_invalid") from None


def call_state(items: tuple[WorkingItem, ...], call_id: str) -> str | None:
    state = None
    for item in items:
        if item.data.get("call_id") != call_id:
            continue
        if item.kind in {"capability_result", "capability_error"}:
            state = "completed"
        elif item.kind == "plan_step_proposed":
            state = "proposed"
        elif item.kind in {"assistant_decision", "capability_call"} and state is None:
            state = "pending"
    return state


def _validate_item(item: WorkingItem) -> None:
    if item.kind not in _ALLOWED_KINDS:
        raise WorkingTranscriptError("agent_working_item_kind_invalid")
    maximum = (
        MAX_RESULT_BYTES
        if item.kind
        in {
            "capability_result",
            "capability_error",
            "plan_execution_error",
            "verified_effect_receipt",
        }
        else 16 * 1024
    )
    _bounded(item.data, maximum, "agent_working_item_too_large")
    call_id = item.data.get("call_id")
    if call_id is not None and (
        not isinstance(call_id, str) or _CALL_ID_RE.fullmatch(call_id) is None
    ):
        raise WorkingTranscriptError("agent_working_call_id_invalid")
    if (
        item.kind
        in {
            "assistant_decision",
            "capability_call",
            "capability_result",
            "capability_error",
            "plan_step_proposed",
        }
        and call_id is None
    ):
        raise WorkingTranscriptError("agent_working_call_id_missing")


def _validate_call_ids(items: tuple[WorkingItem, ...]) -> None:
    decisions = {}
    terminals = set()
    for item in items:
        call_id = item.data.get("call_id")
        if item.kind == "assistant_decision" and call_id is not None:
            signature = (
                item.data.get("decision_kind"),
                item.data.get("capability"),
                _canonical(item.data.get("arguments", {})),
            )
            existing = decisions.get(call_id)
            if existing is not None and existing != signature:
                raise WorkingTranscriptError("agent_working_call_id_conflict")
            if existing is not None:
                raise WorkingTranscriptError("agent_working_call_id_duplicate")
            decisions[call_id] = signature
        if item.kind in {"capability_result", "capability_error"}:
            if call_id in terminals:
                raise WorkingTranscriptError("agent_working_call_terminal_duplicate")
            terminals.add(call_id)


def _bounded(value: object, maximum: int, code: str) -> None:
    try:
        raw = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise WorkingTranscriptError(code) from None
    if len(raw) > maximum:
        raise WorkingTranscriptError(code)


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        raise WorkingTranscriptError("agent_working_transcript_invalid") from None
