"""Bounded deterministic orchestration for the M2 current-record turn."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol, cast
from uuid import UUID, uuid4

from odoo_ai.contracts import (
    ContextPack,
    ContextReadTurnRequest,
    ContextReadTurnResponse,
    ConversationState,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    InstanceProfileSummary,
    RecordRef,
    RecordSnapshot,
    ScreenContext,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
)
from odoo_ai.ports import OdooGateway

MAX_SCREEN_AGE_SECONDS: Final = 300
MAX_SCREEN_FUTURE_SKEW_SECONDS: Final = 30
MAX_ODOO_ID: Final = 2_147_483_647
MAX_SELECTED_IDS: Final = 8
MAX_ACTIVE_COMPANIES: Final = 16
FIELD_CANDIDATES: Final = ("display_name", "name", "state", "company_id")
ALLOWED_VIEW_TYPES: Final = frozenset(
    {"activity", "calendar", "form", "graph", "kanban", "list", "pivot"}
)


class GatewayFactory(Protocol):
    def for_turn(
        self, *, turn_id: UUID, delegation_token: Any
    ) -> OdooGateway: ...


@dataclass(frozen=True, slots=True)
class TraceEventData:
    """One sanitized event awaiting best-effort persistence."""

    event_name: str
    status: str
    attributes: Mapping[str, object]


InstanceLoader = Callable[[], InstanceProfileSummary]
TraceWriter = Callable[[UUID, tuple[TraceEventData, ...]], None]
Clock = Callable[[], datetime]
EventCallback = Callable[[str, str, Mapping[str, object]], None]


class ContextReadError(RuntimeError):
    """Sanitized workflow failure suitable for the Odoo server boundary."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class CurrentRecordRead:
    """Deterministic current-record result shared by M2 and M4 workflows."""

    fields: tuple[str, ...]
    snapshot: RecordSnapshot
    evidence: Evidence


class CurrentRecordReader:
    """Read exactly one delegated current record with reusable validation."""

    def __init__(self, gateway_factory: GatewayFactory) -> None:
        self._gateway_factory = gateway_factory

    async def read(
        self,
        request: ContextReadTurnRequest,
        *,
        event: EventCallback = lambda name, status, attributes: None,
    ) -> CurrentRecordRead:
        gateway = self._gateway_factory.for_turn(
            turn_id=request.turn_id,
            delegation_token=request.delegation_token,
        )
        event("tool.requested", "ok", {"operation": "fields_get"})
        try:
            metadata = await gateway.get_model_metadata(cast(str, request.screen.model))
            fields = _select_fields(metadata)
        except Exception as error:
            event(
                "tool.completed",
                "error",
                {
                    "error_code": _sanitized_error_code(error),
                    "operation": "fields_get",
                },
            )
            raise
        event(
            "tool.completed",
            "ok",
            {"field_count": len(fields), "operation": "fields_get"},
        )
        event("tool.requested", "ok", {"operation": "read_records"})
        try:
            snapshots = await gateway.read_records(
                [
                    RecordRef(
                        model=cast(str, request.screen.model),
                        id=cast(int, request.screen.res_id),
                    )
                ],
                list(fields),
            )
            snapshot = _single_snapshot(
                snapshots,
                model=cast(str, request.screen.model),
                record_id=cast(int, request.screen.res_id),
                fields=fields,
            )
        except Exception as error:
            event(
                "tool.completed",
                "error",
                {
                    "error_code": _sanitized_error_code(error),
                    "operation": "read_records",
                },
            )
            raise
        event(
            "tool.completed",
            "ok",
            {"operation": "read_records", "record_count": 1},
        )
        return CurrentRecordRead(
            fields=fields,
            snapshot=snapshot,
            evidence=_record_evidence(snapshot),
        )


class ContextReadService:
    """Re-read exactly the current record through the per-turn OdooGateway."""

    def __init__(
        self,
        *,
        gateway_factory: GatewayFactory,
        instance_loader: InstanceLoader = lambda: InstanceProfileSummary(
            instance_id="unknown"
        ),
        trace_writer: TraceWriter = lambda trace_id, events: None,
        clock: Clock | None = None,
    ) -> None:
        self._instance_loader = instance_loader
        self._trace_writer = trace_writer
        self._clock = clock or _utc_now
        self._record_reader = CurrentRecordReader(gateway_factory)

    async def run(self, request: ContextReadTurnRequest) -> ContextReadTurnResponse:
        started = time.monotonic()
        events: list[TraceEventData] = []
        self._event(events, "turn.started", "ok", {"turn_id": str(request.turn_id)})
        try:
            now = self._validated_now()
            validate_context_turn_request(request, now=now)
            instance = self._safe_instance_summary()
            context = ContextPack(
                request=UserRequest(message=request.message),
                screen=request.screen,
                user=request.user,
                instance=instance,
                conversation_state=ConversationState(current_screen=request.screen),
                limits=TurnLimits(max_tool_calls=2, max_evidence_items=2),
            )
            self._event(
                events,
                "context.prepared",
                "ok",
                {
                    "instance_state": (
                        "unknown" if context.instance.instance_id == "unknown" else "detected"
                    ),
                    "model": request.screen.model,
                    "record_count": 1,
                },
            )
            current = await self._record_reader.read(
                request,
                event=lambda name, status, attributes: self._event(
                    events, name, status, attributes
                ),
            )
            fields = current.fields
            snapshot = current.snapshot
            evidence = current.evidence
            self._event(
                events,
                "evidence.added",
                "ok",
                {"evidence_count": 1, "evidence_kind": "record"},
            )
            completed_at = self._validated_now()
            response = ContextReadTurnResponse(
                turn_id=request.turn_id,
                message=(
                    "El registro actual se ha releído mediante ORM con los permisos "
                    "efectivos del usuario de Odoo."
                ),
                instance_state=(
                    "unknown" if instance.instance_id == "unknown" else "detected"
                ),
                instance_id=(None if instance.instance_id == "unknown" else instance.instance_id),
                fields_read=fields,
                record=snapshot,
                evidence=evidence,
                completed_at=completed_at,
            )
            _reject_secret_in_response(
                response, request.delegation_token.get_secret_value()
            )
            self._event(
                events,
                "turn.completed",
                "ok",
                {
                    "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                    "record_count": 1,
                },
            )
            return response
        except ContextReadError as error:
            self._event(
                events,
                "turn.completed",
                "error",
                {
                    "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                    "error_code": error.code,
                },
            )
            raise
        except Exception as error:
            code, status_code = _gateway_failure(error)
            self._event(
                events,
                "turn.completed",
                "error",
                {
                    "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                    "error_code": code,
                },
            )
            raise ContextReadError(code, status_code) from None
        finally:
            try:
                self._trace_writer(request.turn_id, tuple(events))
            except Exception:
                pass

    def _validated_now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ContextReadError("clock_unavailable", 503)
        return now.astimezone(UTC)

    def _safe_instance_summary(self) -> InstanceProfileSummary:
        try:
            result = self._instance_loader()
        except Exception:
            return InstanceProfileSummary(instance_id="unknown")
        return (
            result
            if isinstance(result, InstanceProfileSummary)
            else InstanceProfileSummary(instance_id="unknown")
        )

    @staticmethod
    def _event(
        events: list[TraceEventData],
        event_name: str,
        status: str,
        attributes: Mapping[str, object],
    ) -> None:
        events.append(
            TraceEventData(
                event_name=event_name,
                status=status,
                attributes=dict(attributes),
            )
        )


def validate_context_turn_request(request: ContextReadTurnRequest, *, now: datetime) -> None:
    """Apply the single M2/M4 screen and effective-user validation policy."""

    _validate_turn_request(request, now=now, require_record=True)


def validate_query_turn_request(request: ContextReadTurnRequest, *, now: datetime) -> None:
    """Apply the shared screen/user policy while allowing model-only list context."""

    _validate_turn_request(request, now=now, require_record=False)


def validate_how_to_turn_request(request: ContextReadTurnRequest, *, now: datetime) -> None:
    """Apply HOW_TO validation while allowing navigation-only screen context."""

    _validate_turn_request(request, now=now, require_record=False, require_model=False)


class TurnContextRequest(Protocol):
    screen: ScreenContext
    user: UserExecutionContext


def validate_agent_turn_request(request: TurnContextRequest, *, now: datetime) -> None:
    """Validate a unified turn without requiring a current model or record."""

    _validate_turn_request(request, now=now, require_record=False, require_model=False)


def _validate_turn_request(
    request: TurnContextRequest,
    *,
    now: datetime,
    require_record: bool,
    require_model: bool = True,
) -> None:
    screen = request.screen
    if (require_model and not screen.model) or (require_record and screen.res_id is None):
        raise ContextReadError("record_context_required", 422)
    if screen.model is not None and not _valid_model(screen.model):
        raise ContextReadError("invalid_screen", 422)
    if screen.model is None and screen.res_id is not None:
        raise ContextReadError("invalid_screen", 422)
    if screen.res_id is not None and (
        type(screen.res_id) is not int or not 1 <= screen.res_id <= MAX_ODOO_ID
    ):
        raise ContextReadError("invalid_screen", 422)
    for value in (screen.action_id, screen.menu_id):
        if value is not None and (
            type(value) is not int or not 1 <= value <= MAX_ODOO_ID
        ):
            raise ContextReadError("invalid_screen", 422)
    if screen.view_type is not None and screen.view_type not in ALLOWED_VIEW_TYPES:
        raise ContextReadError("invalid_screen", 422)
    if (
        len(screen.selected_ids) > MAX_SELECTED_IDS
        or len(screen.selected_ids) != len(set(screen.selected_ids))
        or any(
            type(value) is not int or not 1 <= value <= MAX_ODOO_ID
            for value in screen.selected_ids
        )
    ):
        raise ContextReadError("invalid_screen", 422)
    captured_at = screen.captured_at
    if captured_at.tzinfo is None:
        raise ContextReadError("invalid_screen", 422)
    captured_at = captured_at.astimezone(UTC)
    if captured_at < now - timedelta(seconds=MAX_SCREEN_AGE_SECONDS):
        raise ContextReadError("screen_expired", 422)
    if captured_at > now + timedelta(seconds=MAX_SCREEN_FUTURE_SKEW_SECONDS):
        raise ContextReadError("screen_from_future", 422)
    user = request.user
    if (
        type(user.uid) is not int
        or not 1 <= user.uid <= MAX_ODOO_ID
        or type(user.company_id) is not int
        or not 1 <= user.company_id <= MAX_ODOO_ID
        or not 1 <= len(user.allowed_company_ids) <= MAX_ACTIVE_COMPANIES
        or len(user.allowed_company_ids) != len(set(user.allowed_company_ids))
        or user.company_id not in user.allowed_company_ids
        or any(
            type(value) is not int or not 1 <= value <= MAX_ODOO_ID
            for value in user.allowed_company_ids
        )
    ):
        raise ContextReadError("invalid_user_context", 422)


def _select_fields(metadata: Evidence) -> tuple[str, ...]:
    if metadata.kind is not EvidenceKind.METADATA or metadata.status is not EvidenceStatus.CHECKED:
        raise ContextReadError("invalid_metadata", 502)
    raw_fields = metadata.payload.get("fields")
    if not isinstance(raw_fields, dict):
        raise ContextReadError("invalid_metadata", 502)
    selected = tuple(name for name in FIELD_CANDIDATES if name in raw_fields)
    if not selected:
        raise ContextReadError("no_readable_fields", 403)
    return selected


def _single_snapshot(
    snapshots: list[RecordSnapshot],
    *,
    model: str,
    record_id: int,
    fields: tuple[str, ...],
) -> RecordSnapshot:
    if len(snapshots) != 1:
        raise ContextReadError("invalid_gateway_response", 502)
    snapshot = snapshots[0]
    if (
        snapshot.record.model != model
        or snapshot.record.id != record_id
        or set(snapshot.fields) != set(fields)
    ):
        raise ContextReadError("invalid_gateway_response", 502)
    return snapshot


def _record_evidence(snapshot: RecordSnapshot) -> Evidence:
    canonical = json.dumps(
        snapshot.model_dump(mode="json"),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return Evidence(
        evidence_id=uuid4(),
        kind=EvidenceKind.RECORD,
        status=EvidenceStatus.CHECKED,
        title="Registro Odoo releído",
        summary="Registro releído mediante ORM bajo la delegación efectiva de Odoo.",
        payload=cast(Any, snapshot.model_dump(mode="json")),
        pointer={"model": snapshot.record.model, "res_id": snapshot.record.id},
        observed_at=snapshot.captured_at,
        sensitivity=EvidenceSensitivity.NORMAL,
        fingerprint=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
    )


def _reject_secret_in_response(
    response: ContextReadTurnResponse, delegation_token: str
) -> None:
    serialized = response.model_dump_json()
    if delegation_token and delegation_token in serialized:
        raise ContextReadError("unsafe_gateway_response", 502)


def _valid_model(value: str) -> bool:
    if not 1 <= len(value) <= 128 or not (value[0].isalpha() or value[0] == "_"):
        return False
    return all(character.isalnum() or character in "_." for character in value)


def _sanitized_error_code(error: Exception) -> str:
    code = getattr(error, "code", "tool_failed")
    if (
        not isinstance(code, str)
        or not 1 <= len(code) <= 64
        or any(
            not (character.islower() or character.isdigit() or character == "_")
            for character in code
        )
    ):
        return "tool_failed"
    return code


def _gateway_failure(error: Exception) -> tuple[str, int]:
    code = getattr(error, "code", "service_unavailable")
    if code in {"access_denied", "delegation_rejected"}:
        return "access_denied", 403
    if code in {"invalid_request", "request_too_large"}:
        return code, 413 if code == "request_too_large" else 422
    if code in {"malformed_response", "response_too_large"}:
        return "invalid_gateway_response", 502
    return "service_unavailable", 503


def _utc_now() -> datetime:
    return datetime.now(UTC)
