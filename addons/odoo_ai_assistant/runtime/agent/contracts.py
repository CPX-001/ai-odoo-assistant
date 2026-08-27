"""Strict provider-neutral decisions for the host-owned agent loop."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TypeAlias

JsonObject: TypeAlias = dict[str, object]

_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_CALL_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_CONFIDENCE = frozenset({"high", "medium", "low"})
_MAX_ARGUMENT_BYTES = 16 * 1024


class NextDecisionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FinalAnswer:
    kind: str
    answer: str
    confidence: str


@dataclass(frozen=True, slots=True)
class ReasoningCapabilityCall:
    kind: str
    call_id: str
    capability: str
    arguments: JsonObject


@dataclass(frozen=True, slots=True)
class PlanStepProposal:
    kind: str
    call_id: str
    capability: str
    arguments: JsonObject
    user_summary: str


NextDecision: TypeAlias = FinalAnswer | ReasoningCapabilityCall | PlanStepProposal


def parse_next_decision(value: object) -> NextDecision:
    if not isinstance(value, dict):
        raise NextDecisionError("agent_next_decision_invalid")
    kind = value.get("kind")
    if kind == "final_answer":
        if set(value) != {"kind", "answer", "confidence"}:
            raise NextDecisionError("agent_next_decision_invalid")
        answer = value.get("answer")
        confidence = value.get("confidence")
        if (
            not isinstance(answer, str)
            or not 1 <= len(answer.strip()) <= 16_384
            or "\x00" in answer
            or confidence not in _CONFIDENCE
        ):
            raise NextDecisionError("agent_next_decision_invalid")
        return FinalAnswer(kind=kind, answer=answer.strip(), confidence=confidence)
    if kind == "reasoning_capability_call":
        if set(value) != {"kind", "call_id", "capability", "arguments"}:
            raise NextDecisionError("agent_next_decision_invalid")
        return ReasoningCapabilityCall(
            kind=kind,
            call_id=_call_id(value.get("call_id")),
            capability=_capability(value.get("capability")),
            arguments=_arguments(value.get("arguments")),
        )
    if kind == "plan_step_proposal":
        if set(value) != {"kind", "call_id", "capability", "arguments", "user_summary"}:
            raise NextDecisionError("agent_next_decision_invalid")
        summary = value.get("user_summary")
        if (
            not isinstance(summary, str)
            or not 1 <= len(summary.strip()) <= 512
            or "\x00" in summary
        ):
            raise NextDecisionError("agent_next_decision_invalid")
        return PlanStepProposal(
            kind=kind,
            call_id=_call_id(value.get("call_id")),
            capability=_capability(value.get("capability")),
            arguments=_arguments(value.get("arguments")),
            user_summary=" ".join(summary.split()),
        )
    raise NextDecisionError("agent_next_decision_kind_invalid")


def decision_payload(decision: NextDecision) -> JsonObject:
    if isinstance(decision, FinalAnswer):
        return {"kind": decision.kind, "answer": decision.answer, "confidence": decision.confidence}
    if isinstance(decision, ReasoningCapabilityCall):
        return {
            "kind": decision.kind,
            "call_id": decision.call_id,
            "capability": decision.capability,
            "arguments": dict(decision.arguments),
        }
    if isinstance(decision, PlanStepProposal):
        return {
            "kind": decision.kind,
            "call_id": decision.call_id,
            "capability": decision.capability,
            "arguments": dict(decision.arguments),
            "user_summary": decision.user_summary,
        }
    raise NextDecisionError("agent_next_decision_invalid")


def next_decision_schema() -> JsonObject:
    capability = {"type": "string", "minLength": 3, "maxLength": 128}
    call_id = {"type": "string", "minLength": 1, "maxLength": 256}
    arguments = {"type": "object"}
    return {
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"const": "final_answer"},
                    "answer": {"type": "string", "minLength": 1, "maxLength": 16384},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["kind", "answer", "confidence"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"const": "reasoning_capability_call"},
                    "call_id": call_id,
                    "capability": capability,
                    "arguments": arguments,
                },
                "required": ["kind", "call_id", "capability", "arguments"],
            },
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"const": "plan_step_proposal"},
                    "call_id": call_id,
                    "capability": capability,
                    "arguments": arguments,
                    "user_summary": {"type": "string", "minLength": 1, "maxLength": 512},
                },
                "required": ["kind", "call_id", "capability", "arguments", "user_summary"],
            },
        ]
    }


def _call_id(value: object) -> str:
    if not isinstance(value, str) or _CALL_ID_RE.fullmatch(value) is None:
        raise NextDecisionError("agent_next_decision_call_id_invalid")
    return value


def _capability(value: object) -> str:
    if not isinstance(value, str) or _CAPABILITY_RE.fullmatch(value) is None or len(value) > 128:
        raise NextDecisionError("agent_next_decision_capability_invalid")
    return value


def _arguments(value: object) -> JsonObject:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise NextDecisionError("agent_next_decision_arguments_invalid")
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise NextDecisionError("agent_next_decision_arguments_invalid") from None
    if len(encoded) > _MAX_ARGUMENT_BYTES:
        raise NextDecisionError("agent_next_decision_arguments_invalid")
    return dict(value)
