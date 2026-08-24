"""Read-only general chat orchestration for source, knowledge and conversation context."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from odoo_ai.adapters.codex_engine import CodexAppServerEngine, CodexEngineError
from odoo_ai.adapters.codex_runtime import CodexRuntimeSettings
from odoo_ai.adapters.source_tools import SourceToolExecutorFactory, source_tool_specs
from odoo_ai.contracts import (
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    Evidence,
    InstanceProfileSummary,
    KnowledgeReadExcerptRequest,
    KnowledgeSearchRequest,
    TurnLimits,
    UserRequest,
    Workflow,
)
from odoo_ai.contracts.chat import GeneralTurnRequest, GeneralTurnResponse
from odoo_ai.knowledge import (
    KnowledgeRetrievalError,
    KnowledgeRetrievalService,
    SqlAlchemyKnowledgeRetrievalStore,
)
from odoo_ai.storage import (
    DatabaseConfigurationError,
    DatabaseSettings,
    create_database_engine,
    create_session_factory,
    get_instance_profile,
    session_scope,
)
from odoo_ai.storage.chat_repository import ChatStoreError, recent_chat_text

_GENERAL_MAX_TOOL_CALLS = 8
_GENERAL_MAX_EVIDENCE = 16
_STOP_WORDS = frozenset(
    {
        "como",
        "cómo",
        "para",
        "porque",
        "porqué",
        "donde",
        "dónde",
        "cuando",
        "cuándo",
        "esta",
        "este",
        "esto",
        "that",
        "this",
        "what",
        "where",
        "when",
        "with",
        "from",
        "odoo",
    }
)


class GeneralChatError(RuntimeError):
    def __init__(self, code: str, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class GeneralChatService:
    """Give Codex broad read context without granting broad Odoo authority."""

    def __init__(self, *, database_settings: DatabaseSettings) -> None:
        self._database_settings = database_settings

    @classmethod
    def from_env(cls) -> GeneralChatService:
        return cls(database_settings=DatabaseSettings.from_env())

    async def run(self, request: GeneralTurnRequest) -> GeneralTurnResponse:
        history, knowledge = await asyncio.gather(
            asyncio.to_thread(self._history_sync, request),
            asyncio.to_thread(self._knowledge_sync, request),
        )
        context = ContextPack(
            request=UserRequest(message=request.message),
            screen=request.screen,
            user=request.user,
            workflow_hint=None,
            instance=InstanceProfileSummary(instance_id=f"odoo:{request.actor.database}"),
            retrieved_evidence=list(knowledge),
            conversation_state=ConversationState(
                current_screen=request.screen,
                short_summary=history,
            ),
            limits=TurnLimits(
                max_tool_calls=_GENERAL_MAX_TOOL_CALLS,
                max_evidence_items=_GENERAL_MAX_EVIDENCE,
            ),
        )

        try:
            settings = CodexRuntimeSettings.from_env()
        except (OSError, RuntimeError, ValueError):
            raise GeneralChatError("engine_unavailable") from None

        source_factory: SourceToolExecutorFactory | None = None
        try:
            source_factory = SourceToolExecutorFactory.from_env()
        except (OSError, RuntimeError, ValueError):
            pass

        if source_factory is not None:
            engine = CodexAppServerEngine(
                settings,
                tool_executor_factory=source_factory,
            )
            try:
                answer = await engine.run_turn(
                    context,
                    list(source_tool_specs()),
                    AnswerEnvelope.model_json_schema(),
                )
            except CodexEngineError as error:
                if not error.code.startswith("source_"):
                    raise GeneralChatError(_engine_code(error.code)) from None
                answer = await self._run_without_source(settings, context)
        else:
            answer = await self._run_without_source(settings, context)

        if answer.workflow is Workflow.ACTION or answer.proposed_action is not None:
            raise GeneralChatError("invalid_response", 502)
        if len(answer.answer_markdown) > 16_384:
            raise GeneralChatError("invalid_response", 502)
        return GeneralTurnResponse(
            turn_id=request.turn_id,
            workflow=answer.workflow,
            answer_markdown=answer.answer_markdown,
            confidence=answer.confidence,
            limitations=tuple(answer.limitations),
            evidence_refs=tuple(answer.evidence_refs),
            completed_at=datetime.now(UTC),
        )

    async def _run_without_source(
        self, settings: CodexRuntimeSettings, context: ContextPack
    ) -> AnswerEnvelope:
        fallback = CodexAppServerEngine(settings)
        try:
            return await fallback.run_turn(
                context,
                [],
                AnswerEnvelope.model_json_schema(),
            )
        except CodexEngineError as error:
            raise GeneralChatError(_engine_code(error.code)) from None

    def _history_sync(self, request: GeneralTurnRequest) -> str:
        if request.conversation_id is None:
            return ""
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                return recent_chat_text(
                    session,
                    actor=request.actor,
                    conversation_id=request.conversation_id,
                )
        except ChatStoreError:
            return ""
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            return ""
        finally:
            if engine is not None:
                engine.dispose()

    def _knowledge_sync(self, request: GeneralTurnRequest) -> tuple[Evidence, ...]:
        query = _knowledge_query(request.message)
        if query is None:
            return ()
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                profile = get_instance_profile(
                    session,
                    instance_id=f"odoo:{request.actor.database}",
                )
                if profile is None:
                    return ()
                retrieval = KnowledgeRetrievalService(
                    store=SqlAlchemyKnowledgeRetrievalStore(session)
                )
                result = retrieval.search(
                    instance_profile_id=profile.id,
                    request=KnowledgeSearchRequest(query=query, top_k=3),
                )
                evidence: list[Evidence] = []
                for candidate in result.candidates[:2]:
                    excerpt = retrieval.read_excerpt(
                        instance_profile_id=profile.id,
                        request=KnowledgeReadExcerptRequest(
                            ref=candidate.ref,
                            max_lines=30,
                            max_chars=3_000,
                            max_bytes=6_000,
                        ),
                    )
                    evidence.append(excerpt.evidence)
                return tuple(evidence)
        except (
            DatabaseConfigurationError,
            KnowledgeRetrievalError,
            SQLAlchemyError,
            OSError,
            ValueError,
        ):
            return ()
        finally:
            if engine is not None:
                engine.dispose()


def _knowledge_query(message: str) -> str | None:
    words = [
        value.casefold()
        for value in re.findall(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_.-]{2,}", message)
    ]
    candidates = [value for value in words if value not in _STOP_WORDS]
    if not candidates:
        return None
    return max(candidates, key=len)[:256]


def _engine_code(code: str) -> str:
    if "timeout" in code or "deadline" in code:
        return "engine_timeout"
    return "engine_unavailable"
