from types import SimpleNamespace
from uuid import uuid4

from odoo_ai.contracts.chat import ChatActor
from odoo_ai.runtime import agent as runtime_agent


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def commit(self):
        return None

    def rollback(self):
        return None


def _fail_engine_creation(settings):
    del settings
    raise AssertionError("engine creation in hot path")


def test_history_reuses_runtime_session_factory_without_creating_an_engine(monkeypatch) -> None:
    factory = object.__new__(runtime_agent.RuntimeAgentFactory)
    factory._sessions = lambda: FakeSession()

    monkeypatch.setattr(runtime_agent, "create_database_engine", _fail_engine_creation)
    monkeypatch.setattr(
        runtime_agent,
        "recent_chat_text",
        lambda session, *, actor, conversation_id: "recent history",
    )
    request = SimpleNamespace(
        conversation_id=uuid4(),
        actor=ChatActor(database="customer", uid=7),
    )

    assert factory._history_sync(request) == "recent history"


def test_instance_summary_reuses_runtime_session_factory_without_creating_engine(
    monkeypatch,
) -> None:
    factory = object.__new__(runtime_agent.RuntimeAgentFactory)
    factory._sessions = lambda: FakeSession()

    monkeypatch.setattr(runtime_agent, "create_database_engine", _fail_engine_creation)
    monkeypatch.setattr(runtime_agent, "get_latest_instance_profile", lambda session: None)

    summary = factory._load_instance_summary_shared()

    assert summary.instance_id == "unknown"
