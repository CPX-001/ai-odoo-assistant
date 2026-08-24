"""Runtime facade for persistent chat history in the Assistant PostgreSQL database."""

from __future__ import annotations

import asyncio
import re

from sqlalchemy.exc import SQLAlchemyError

from odoo_ai.adapters.chat_routing import CodexChatRoutingInterpreter
from odoo_ai.adapters.codex_runtime import CodexRuntimeSettings
from odoo_ai.adapters.source_tools import SourceToolExecutorFactory, source_tool_specs
from odoo_ai.adapters.user_model_engine import UserSelectableCodexAppServerEngine as CodexAppServerEngine
from odoo_ai.application.chat_routing import ChatRoutingService
from odoo_ai.application.general_chat import GeneralChatService
from odoo_ai.contracts import (
    Evidence,
    KnowledgeReadExcerptRequest,
    KnowledgeSearchRequest,
)
from odoo_ai.contracts.chat import (
    ChatAppendRequest,
    ChatAppendResponse,
    ChatHistoryRequest,
    ChatHistoryResponse,
    ChatRouteRequest,
    GeneralTurnRequest,
)
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
from odoo_ai.storage.chat_repository import (
    ChatStoreError,
    append_chat_exchange,
    load_chat_history,
    recent_chat_text,
)

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


class RuntimeChatError(RuntimeError):
    def __init__(self, code: str, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class RuntimeChatHistoryService:
    def __init__(self, *, database_settings: DatabaseSettings) -> None:
        self._database_settings = database_settings

    @classmethod
    def from_env(cls) -> RuntimeChatHistoryService:
        return cls(database_settings=DatabaseSettings.from_env())

    async def history(self, request: ChatHistoryRequest) -> ChatHistoryResponse:
        return await asyncio.to_thread(self._history_sync, request)

    async def append(self, request: ChatAppendRequest) -> ChatAppendResponse:
        return await asyncio.to_thread(self._append_sync, request)

    def _history_sync(self, request: ChatHistoryRequest) -> ChatHistoryResponse:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                return load_chat_history(
                    session,
                    actor=request.actor,
                    conversation_id=request.conversation_id,
                    max_conversations=request.max_conversations,
                    max_messages=request.max_messages,
                )
        except ChatStoreError as error:
            raise RuntimeChatError(error.code, 404) from None
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise RuntimeChatError("chat_store_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()

    def _append_sync(self, request: ChatAppendRequest) -> ChatAppendResponse:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                return append_chat_exchange(
                    session,
                    actor=request.actor,
                    conversation_id=request.conversation_id,
                    user_message=request.user_message,
                    assistant_message=request.assistant_message,
                    internal_workflow=request.internal_workflow,
                )
        except ChatStoreError as error:
            raise RuntimeChatError(error.code, 404) from None
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise RuntimeChatError("chat_store_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()


class RuntimeGeneralChatContext:
    """Load optional chat and knowledge context from Assistant-owned storage."""

    def __init__(self, *, database_settings: DatabaseSettings) -> None:
        self._database_settings = database_settings

    async def history(self, request: GeneralTurnRequest) -> str:
        return await asyncio.to_thread(self._history_sync, request)

    async def knowledge(self, request: GeneralTurnRequest) -> tuple[Evidence, ...]:
        return await asyncio.to_thread(self._knowledge_sync, request)

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


class RuntimeChatRoutingContext:
    """Load only bounded Assistant-owned conversation text for intent continuity."""

    def __init__(self, *, database_settings: DatabaseSettings) -> None:
        self._database_settings = database_settings

    async def history(self, request: ChatRouteRequest) -> str:
        return await asyncio.to_thread(self._history_sync, request)

    def _history_sync(self, request: ChatRouteRequest) -> str:
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


def create_runtime_general_chat_service() -> GeneralChatService:
    """Compose the application service with concrete runtime adapters."""

    database_settings = DatabaseSettings.from_env()
    codex_settings = CodexRuntimeSettings.from_env()
    context = RuntimeGeneralChatContext(database_settings=database_settings)
    source_factory: SourceToolExecutorFactory | None = None
    try:
        source_factory = SourceToolExecutorFactory.from_env()
    except (OSError, RuntimeError, ValueError):
        pass
    if source_factory is None:
        return GeneralChatService(
            reasoning_engine=CodexAppServerEngine(codex_settings),
            history_loader=context.history,
            knowledge_loader=context.knowledge,
        )
    return GeneralChatService(
        reasoning_engine=CodexAppServerEngine(
            codex_settings,
            tool_executor_factory=source_factory,
        ),
        history_loader=context.history,
        knowledge_loader=context.knowledge,
        tools=source_tool_specs(),
        fallback_engine=CodexAppServerEngine(codex_settings),
    )


def create_runtime_chat_routing_service() -> ChatRoutingService:
    """Compose multilingual interpretation without granting the provider authority."""

    database_settings = DatabaseSettings.from_env()
    codex_settings = CodexRuntimeSettings.from_env()
    context = RuntimeChatRoutingContext(database_settings=database_settings)
    interpreter = CodexChatRoutingInterpreter(BaseCodexAppServerEngine(codex_settings))
    return ChatRoutingService(
        interpreter=interpreter,
        history_loader=context.history,
    )


def _knowledge_query(message: str) -> str | None:
    words = [
        value.casefold()
        for value in re.findall(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_.-]{2,}", message)
    ]
    candidates = [value for value in words if value not in _STOP_WORDS]
    if not candidates:
        return None
    return str(max(candidates, key=len)[:256])
