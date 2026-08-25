"""Runtime facade for bounded Assistant chat deletion."""

from __future__ import annotations

import asyncio

from sqlalchemy.exc import SQLAlchemyError

from odoo_ai.contracts.chat_delete import ChatDeleteRequest, ChatDeleteResponse
from odoo_ai.storage import (
    DatabaseConfigurationError,
    DatabaseSettings,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from odoo_ai.storage.chat_delete_repository import delete_chat_conversations
from odoo_ai.storage.chat_repository import ChatStoreError


class RuntimeChatDeleteError(RuntimeError):
    def __init__(self, code: str, status_code: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class RuntimeChatDeleteService:
    def __init__(self, *, database_settings: DatabaseSettings) -> None:
        self._database_settings = database_settings

    @classmethod
    def from_env(cls) -> "RuntimeChatDeleteService":
        return cls(database_settings=DatabaseSettings.from_env())

    async def delete(self, request: ChatDeleteRequest) -> ChatDeleteResponse:
        return await asyncio.to_thread(self._delete_sync, request)

    def _delete_sync(self, request: ChatDeleteRequest) -> ChatDeleteResponse:
        engine = None
        try:
            engine = create_database_engine(self._database_settings)
            factory = create_session_factory(engine)
            with session_scope(factory) as session:
                return delete_chat_conversations(
                    session,
                    actor=request.actor,
                    conversation_ids=request.conversation_ids,
                )
        except ChatStoreError as error:
            raise RuntimeChatDeleteError(error.code, 404) from None
        except (DatabaseConfigurationError, SQLAlchemyError, OSError, ValueError):
            raise RuntimeChatDeleteError("chat_store_unavailable", 503) from None
        finally:
            if engine is not None:
                engine.dispose()
