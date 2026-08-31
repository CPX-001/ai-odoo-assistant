import asyncio
import sys
import types
from pathlib import Path

import pytest

ADDON_ROOT = Path(__file__).resolve().parents[2] / "addons/odoo_ai_assistant"
for package_name, package_path in (
    ("_timing_fixture", ADDON_ROOT),
    ("_timing_fixture.runtime", ADDON_ROOT / "runtime"),
    ("_timing_fixture.runtime.agent", ADDON_ROOT / "runtime/agent"),
):
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    sys.modules[package_name] = package

from _timing_fixture.runtime.agent.contracts import FinalAnswer  # noqa: E402
from _timing_fixture.runtime.agent.planning import PlanningDecisionEngine  # noqa: E402
from _timing_fixture.runtime.capabilities.contracts import CapabilityContext  # noqa: E402


class _Provider:
    def __init__(self, *, fail=False):
        self.fail = fail

    async def next_decision(self, **_kwargs):
        if self.fail:
            raise RuntimeError("provider failed")
        return FinalAnswer("final_answer", "ok", "high")


def _context(events):
    return CapabilityContext(
        env=object(),
        turn_id="provider-timing-turn",
        event_sink=lambda event_type, title, payload: events.append(
            (event_type, title, dict(payload))
        ),
    )


def _call(engine, context):
    return asyncio.run(
        engine.next_decision(
            message="Hola",
            conversation_summary="",
            context=context,
            reasoning_capabilities=(),
            planning_capabilities=(),
            working_items=(),
            remaining_budgets={},
        )
    )


def test_provider_decision_timing_is_sanitized_and_non_authoritative():
    events = []
    decision = _call(PlanningDecisionEngine(_Provider()), _context(events))
    assert isinstance(decision, FinalAnswer)
    assert len(events) == 1
    event_type, _title, payload = events[0]
    assert event_type == "diagnostic.provider.decision"
    assert payload["outcome"] == "completed"
    assert payload["duration_ms"] >= 0
    assert set(payload) == {"duration_ms", "outcome"}


def test_failed_provider_decision_records_timing_without_swallowing_failure():
    events = []
    with pytest.raises(RuntimeError, match="provider failed"):
        _call(PlanningDecisionEngine(_Provider(fail=True)), _context(events))
    assert events[0][0] == "diagnostic.provider.decision"
    assert events[0][2]["outcome"] == "failed"
