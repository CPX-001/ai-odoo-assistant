"""Evidence-led orchestration for the read-only HOW_TO workflow."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Final, cast
from uuid import UUID, uuid4

from odoo_ai.application.context_read import (
    Clock,
    ContextReadError,
    GatewayFactory,
    InstanceLoader,
    TraceEventData,
    TraceWriter,
    validate_how_to_turn_request,
)
from odoo_ai.application.effective_schema import EffectiveSchemaService
from odoo_ai.application.navigation import NavigationService
from odoo_ai.contracts import (
    AnswerConfidence,
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    DocumentCitation,
    EffectiveModelSchema,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    HowToCitation,
    HowToTurnRequest,
    HowToTurnResponse,
    InstanceProfileSummary,
    KnowledgeMediaType,
    NavigationCitation,
    NavigationNode,
    SchemaCitation,
    SchemaFieldCitation,
    ToolExecutionReport,
    ToolSpec,
    TurnLimits,
    UserRequest,
    Workflow,
)
from odoo_ai.ports import ReasoningEngine

MAX_HOW_TO_TOOL_CALLS: Final = 6
MAX_HOW_TO_EVIDENCE_ITEMS: Final = 16
MAX_NAVIGATION_EVIDENCE: Final = 8
MAX_ANSWER_BYTES: Final = 64 * 1024
MAX_ANSWER_CHARS: Final = 16_384
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_TECHNICAL_ASSERTION = re.compile(r"`([A-Za-z_][A-Za-z0-9_]{0,127})`")

ReportLoader = Callable[[], ToolExecutionReport]


class HowToTurnError(RuntimeError):
    """Sanitized HOW_TO failure safe for the authenticated Odoo boundary."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class HowToService:
    """Prefetch visible metadata, expose only knowledge tools, and validate citations."""

    def __init__(
        self,
        *,
        gateway_factory: GatewayFactory,
        reasoning_engine: ReasoningEngine,
        knowledge_tools: Sequence[ToolSpec],
        report_loader: ReportLoader = lambda: ToolExecutionReport(),
        instance_loader: InstanceLoader = lambda: InstanceProfileSummary(instance_id="unknown"),
        trace_writer: TraceWriter = lambda trace_id, events: None,
        clock: Clock | None = None,
    ) -> None:
        self._gateway_factory = gateway_factory
        self._reasoning_engine = reasoning_engine
        self._knowledge_tools = tuple(ToolSpec.model_validate(tool) for tool in knowledge_tools)
        self._report_loader = report_loader
        self._instance_loader = instance_loader
        self._trace_writer = trace_writer
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run(self, request: HowToTurnRequest) -> HowToTurnResponse:
        started = time.monotonic()
        events: list[TraceEventData] = []
        report_taken = False
        self._event(events, "turn.started", "ok", {"turn_id": str(request.turn_id)})
        try:
            now = self._validated_now()
            validate_how_to_turn_request(request, now=now)
            instance = self._safe_instance_summary()
            gateway = self._gateway_factory.for_turn(
                turn_id=request.turn_id,
                delegation_token=request.delegation_token,
            )
            navigation_evidence: tuple[Evidence, ...] = ()
            schema_evidence: Evidence | None = None
            try:
                navigation = await NavigationService(gateway).get()
                navigation_evidence = _relevant_navigation_evidence(
                    navigation.navigation.nodes,
                    model=request.screen.model,
                    menu_id=request.screen.menu_id,
                    captured_at=navigation.navigation.captured_at,
                )
                self._event(
                    events,
                    "evidence.added",
                    "ok",
                    {"evidence_kind": "metadata", "provider": "odoo_navigation", "count": len(navigation_evidence)},
                )
            except Exception as error:
                if getattr(error, "code", None) in {"access_denied", "delegation_rejected"}:
                    raise HowToTurnError("access_denied", 403) from None
                self._event(events, "tool.completed", "error", {"operation": "navigation"})
            if request.screen.model is not None:
                try:
                    schema_evidence = (
                        await EffectiveSchemaService(gateway).get(
                            model=request.screen.model,
                            captured_for_user=request.user.uid,
                        )
                    ).evidence
                    self._event(
                        events,
                        "evidence.added",
                        "ok",
                        {"evidence_kind": "metadata", "provider": "effective_schema", "count": 1},
                    )
                except Exception as error:
                    if getattr(error, "code", None) in {"access_denied", "delegation_rejected"}:
                        raise HowToTurnError("access_denied", 403) from None
                    self._event(events, "tool.completed", "error", {"operation": "effective_schema"})
            live = [*navigation_evidence]
            if schema_evidence is not None:
                live.append(schema_evidence)
            context = ContextPack(
                request=UserRequest(message=request.message),
                screen=request.screen,
                user=request.user,
                workflow_hint=Workflow.HOW_TO,
                instance=instance,
                live_evidence=live,
                conversation_state=ConversationState(current_screen=request.screen),
                limits=TurnLimits(
                    max_tool_calls=MAX_HOW_TO_TOOL_CALLS,
                    max_evidence_items=MAX_HOW_TO_EVIDENCE_ITEMS,
                ),
            )
            self._event(
                events,
                "context.prepared",
                "ok",
                {
                    "model": request.screen.model,
                    "navigation_count": len(navigation_evidence),
                    "schema_available": schema_evidence is not None,
                    "workflow": "HOW_TO",
                },
            )
            answer = await self._reasoning_engine.run_turn(
                context,
                list(self._knowledge_tools),
                AnswerEnvelope.model_json_schema(),
            )
            report = self._report_loader()
            report_taken = True
            for evidence in report.retrieved_evidence:
                self._event(
                    events,
                    "evidence.added",
                    "ok",
                    {"evidence_kind": evidence.kind.value, "provider": "knowledge"},
                )
            validated, citations = _validated_answer(
                answer,
                live=live,
                retrieved=report.retrieved_evidence,
                screen_model=request.screen.model,
                navigation_available=_has_relevant_navigation(
                    navigation_evidence, model=request.screen.model
                ),
                schema_available=schema_evidence is not None,
            )
            response = HowToTurnResponse(
                turn_id=request.turn_id,
                answer_markdown=validated.answer_markdown,
                confidence=validated.confidence,
                limitations=tuple(validated.limitations),
                citations=citations,
                completed_at=self._validated_now(),
            )
            _reject_secret(response, request.delegation_token.get_secret_value())
            self._event(
                events,
                "turn.completed",
                "ok",
                {"duration_ms": max(0, int((time.monotonic() - started) * 1000)), "workflow": "HOW_TO"},
            )
            return response
        except HowToTurnError:
            raise
        except ContextReadError as error:
            raise HowToTurnError(error.code, error.status_code) from None
        except Exception as error:
            code, status_code = _how_to_failure(error)
            raise HowToTurnError(code, status_code) from None
        finally:
            if not report_taken:
                try:
                    self._report_loader()
                except Exception:
                    pass
            try:
                self._trace_writer(request.turn_id, tuple(events))
            except Exception:
                pass

    def _validated_now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise HowToTurnError("clock_unavailable", 503)
        return now.astimezone(UTC)

    def _safe_instance_summary(self) -> InstanceProfileSummary:
        try:
            result = self._instance_loader()
        except Exception:
            return InstanceProfileSummary(instance_id="unknown")
        return result if isinstance(result, InstanceProfileSummary) else InstanceProfileSummary(instance_id="unknown")

    @staticmethod
    def _event(
        events: list[TraceEventData],
        name: str,
        status: str,
        attributes: Mapping[str, object],
    ) -> None:
        events.append(TraceEventData(name, status, dict(attributes)))


def _relevant_navigation_evidence(
    nodes: Sequence[NavigationNode],
    *,
    model: str | None,
    menu_id: int | None,
    captured_at: datetime,
) -> tuple[Evidence, ...]:
    by_id = {node.menu_id: node for node in nodes}
    selected: list[NavigationNode] = []
    if menu_id in by_id:
        current: NavigationNode | None = by_id[menu_id]
        lineage: list[NavigationNode] = []
        while current is not None:
            lineage.append(current)
            current = by_id.get(current.parent_id) if current.parent_id is not None else None
        selected.extend(reversed(lineage))
    if model is not None:
        selected.extend(
            node for node in nodes if node.action is not None and node.action.target_model == model
        )
    elif not selected:
        selected.extend(node for node in nodes if node.action is not None)
    unique = list({node.menu_id: node for node in selected}.values())[:MAX_NAVIGATION_EVIDENCE]
    return tuple(_navigation_node_evidence(node, captured_at=captured_at) for node in unique)


def _navigation_node_evidence(node: NavigationNode, *, captured_at: datetime) -> Evidence:
    payload = node.model_dump(mode="json")
    canonical = json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return Evidence(
        evidence_id=uuid4(),
        kind=EvidenceKind.METADATA,
        status=EvidenceStatus.CHECKED,
        title=f"Visible menu: {' > '.join(node.path)}",
        summary="Visible logical menu/action checked under the effective Odoo user.",
        payload=payload,
        pointer={"provider": "odoo_navigation", "menu_id": node.menu_id},
        observed_at=captured_at,
        sensitivity=EvidenceSensitivity.TECHNICAL,
        fingerprint=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
    )


def _has_relevant_navigation(
    evidence: Sequence[Evidence], *, model: str | None
) -> bool:
    for item in evidence:
        action = item.payload.get("action")
        if not isinstance(action, dict):
            continue
        if model is None or action.get("target_model") == model:
            return True
    return False


def _validated_answer(
    answer: AnswerEnvelope,
    *,
    live: Sequence[Evidence],
    retrieved: Sequence[Evidence],
    screen_model: str | None,
    navigation_available: bool,
    schema_available: bool,
) -> tuple[AnswerEnvelope, tuple[HowToCitation, ...]]:
    if answer.workflow is not Workflow.HOW_TO:
        raise HowToTurnError("answer_workflow_invalid", 502)
    if answer.proposed_action is not None:
        raise HowToTurnError("answer_action_not_allowed", 502)
    if (
        not answer.answer_markdown
        or len(answer.answer_markdown) > MAX_ANSWER_CHARS
        or len(answer.answer_markdown.encode()) > MAX_ANSWER_BYTES
    ):
        raise HowToTurnError("answer_invalid", 502)
    limitations = list(dict.fromkeys(answer.limitations))
    if len(limitations) > 8 or any(not value or len(value) > 1_024 for value in limitations):
        raise HowToTurnError("answer_invalid", 502)
    all_evidence = [*live, *retrieved]
    by_id: dict[UUID, Evidence] = {}
    canonical: dict[UUID, str] = {}
    for evidence in all_evidence:
        value = evidence.model_dump_json()
        if evidence.evidence_id in canonical and canonical[evidence.evidence_id] != value:
            raise HowToTurnError("evidence_duplicate_conflict", 502)
        canonical[evidence.evidence_id] = value
        by_id[evidence.evidence_id] = evidence
    refs = tuple(dict.fromkeys(answer.evidence_refs))
    if len(refs) > 24:
        raise HowToTurnError("answer_invalid", 502)
    try:
        cited = tuple(by_id[reference] for reference in refs)
    except KeyError:
        raise HowToTurnError("evidence_ref_unknown", 502) from None
    if any(item.status is not EvidenceStatus.CHECKED for item in cited):
        raise HowToTurnError("evidence_not_checked", 502)
    citations = tuple(_citation(item) for item in cited)
    kinds = {item.kind for item in citations}
    confidence = answer.confidence
    text = answer.answer_markdown
    if not navigation_available:
        text = "No puedo confirmar una ruta de menú visible para esta instalación con el contexto actual."
        confidence = AnswerConfidence.LOW
        citations = tuple(item for item in citations if item.kind == "document")
        kinds = {item.kind for item in citations}
        _add_limitation(limitations, "No se encontró una ruta de menú visible que confirme los pasos en esta instalación.")
    unknown_fields = _unknown_field_assertions(text, live, screen_model)
    if unknown_fields:
        text = "No puedo confirmar el campo solicitado en el esquema efectivo visible de esta instalación."
        confidence = AnswerConfidence.LOW
        _add_limitation(limitations, "El campo mencionado no aparece en el esquema efectivo comprobado y se ha omitido la afirmación.")
    if "document" in kinds and "navigation" not in kinds:
        _add_limitation(limitations, "La documentación citada no confirma por sí sola una ruta visible en esta instalación.")
        if confidence is AnswerConfidence.HIGH:
            confidence = AnswerConfidence.MEDIUM
    required = {"navigation", "document"}
    if screen_model is not None:
        required.add("schema")
    if confidence is AnswerConfidence.HIGH and not required.issubset(kinds):
        confidence = AnswerConfidence.MEDIUM
        _add_limitation(limitations, "La confianza alta requiere navegación, esquema y documentación comprobados en el mismo turno.")
    if schema_available and screen_model is not None and "schema" not in kinds:
        _add_limitation(limitations, "La respuesta no cita el esquema efectivo del modelo actual.")
    if not schema_available and screen_model is not None:
        _add_limitation(
            limitations,
            "No fue posible comprobar el esquema efectivo del modelo actual.",
        )
    if not refs:
        text = "No puedo ofrecer instrucciones específicas de esta instalación sin evidencia comprobada citable."
        confidence = AnswerConfidence.LOW
        _add_limitation(
            limitations,
            "No se obtuvo evidencia comprobada citable; no se presenta conocimiento general como hecho de esta instalación.",
        )
    return (
        answer.model_copy(
            update={
                "answer_markdown": text,
                "confidence": confidence,
                "evidence_refs": list(refs),
                "limitations": limitations[:8],
            }
        ),
        citations,
    )


def _citation(evidence: Evidence) -> HowToCitation:
    pointer = evidence.pointer
    if not isinstance(pointer, dict) or evidence.observed_at is None:
        raise HowToTurnError("how_to_citation_invalid", 502)
    provider = pointer.get("provider")
    if evidence.kind is EvidenceKind.METADATA and provider == "odoo_navigation":
        try:
            node = NavigationNode.model_validate(evidence.payload)
        except ValueError:
            raise HowToTurnError("how_to_citation_invalid", 502) from None
        if pointer.get("menu_id") != node.menu_id:
            raise HowToTurnError("how_to_citation_invalid", 502)
        return NavigationCitation(
            evidence_id=evidence.evidence_id,
            menu_id=node.menu_id,
            path=node.path,
            target_model=node.action.target_model if node.action else None,
            view_modes=node.action.view_modes if node.action else (),
            captured_at=evidence.observed_at,
        )
    if evidence.kind is EvidenceKind.METADATA and provider == "effective_schema":
        try:
            schema = EffectiveModelSchema.model_validate(evidence.payload)
        except ValueError:
            raise HowToTurnError("how_to_citation_invalid", 502) from None
        if pointer.get("model") != schema.model or pointer.get("schema_id") != schema.schema_id:
            raise HowToTurnError("how_to_citation_invalid", 502)
        if evidence.fingerprint != schema.schema_id:
            raise HowToTurnError("how_to_citation_invalid", 502)
        return SchemaCitation(
            evidence_id=evidence.evidence_id,
            model=schema.model,
            schema_id=schema.schema_id,
            fields=tuple(
                SchemaFieldCitation(name=field.name, label=field.label, field_type=field.field_type)
                for field in schema.fields.values()
            ),
            captured_at=evidence.observed_at,
        )
    if evidence.kind is EvidenceKind.DOCUMENT:
        if evidence.fingerprint is None or not _FINGERPRINT.fullmatch(evidence.fingerprint):
            raise HowToTurnError("how_to_citation_invalid", 502)
        required_pointer = {"provider_id", "document_id", "ordinal", "start_line", "end_line"}
        if not required_pointer.issubset(pointer):
            raise HowToTurnError("how_to_citation_invalid", 502)
        payload = evidence.payload
        if (
            payload.get("provider_id") != pointer.get("provider_id")
            or payload.get("document_id") != pointer.get("document_id")
        ):
            raise HowToTurnError("how_to_citation_invalid", 502)
        try:
            provider_id = cast(str, pointer["provider_id"])
            document_id = cast(str, pointer["document_id"])
            return DocumentCitation(
                evidence_id=evidence.evidence_id,
                provider_id=provider_id,
                document_id=document_id,
                title=evidence.title.removeprefix("Document: "),
                locale=cast(str | None, payload.get("locale")),
                media_type=KnowledgeMediaType(cast(str, payload["media_type"])),
                ordinal=cast(int, pointer["ordinal"]),
                start_line=cast(int, pointer["start_line"]),
                end_line=cast(int, pointer["end_line"]),
                fingerprint=evidence.fingerprint,
            )
        except (KeyError, TypeError, ValueError):
            raise HowToTurnError("how_to_citation_invalid", 502) from None
    raise HowToTurnError("how_to_citation_invalid", 502)


def _unknown_field_assertions(
    text: str, evidence: Sequence[Evidence], model: str | None
) -> set[str]:
    if model is None:
        return set()
    fields: set[str] = set()
    for item in evidence:
        if isinstance(item.pointer, dict) and item.pointer.get("provider") == "effective_schema":
            raw = item.payload.get("fields")
            if isinstance(raw, dict):
                fields.update(str(name) for name in raw)
    asserted = {value for value in _TECHNICAL_ASSERTION.findall(text) if "_" in value}
    return asserted - fields


def _add_limitation(values: list[str], value: str) -> None:
    if value not in values and len(values) < 8:
        values.append(value)


def _reject_secret(response: HowToTurnResponse, secret: str) -> None:
    if secret and secret in response.model_dump_json():
        raise HowToTurnError("unsafe_gateway_response", 502)


def _how_to_failure(error: Exception) -> tuple[str, int]:
    code = getattr(error, "code", "engine_unavailable")
    if code in {"access_denied", "delegation_rejected"}:
        return "access_denied", 403
    if code in {"invalid_request", "request_too_large"}:
        return code, 413 if code == "request_too_large" else 422
    if code in {"malformed_response", "response_too_large"}:
        return "invalid_gateway_response", 502
    if isinstance(code, str) and ("timeout" in code or "deadline" in code):
        return "engine_timeout", 504
    if isinstance(code, str) and (
        code.startswith("knowledge_") or code in {"evidence_not_checked"}
    ):
        return "evidence_unavailable", 503
    return "engine_unavailable", 503
