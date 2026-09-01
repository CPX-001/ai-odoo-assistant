"""Real-provider eager/lazy selection comparison for P7-REAL-DISCLOSURE."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from odoo.addons.odoo_ai_assistant.runtime.agent.codex import CodexAgentSettings
from odoo.addons.odoo_ai_assistant.runtime.agent.codex_decision import (
    CodexDecisionEngine,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities import (
    CapabilityContext,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityRisk,
)


def handler(context, arguments):
    del context, arguments
    return {"ok": True}


def definition(index: int) -> CapabilityDefinition:
    name = f"bulk.tool_{index:03d}"
    return CapabilityDefinition(
        name=name,
        title=f"Synthetic bulk tool {index:03d}",
        description=f"Return the deterministic synthetic value for tool {index:03d}.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        risk=CapabilityRisk.READ,
        effect=CapabilityEffect.READ_ONLY,
        handler=handler,
    )


async def select(catalog: tuple[CapabilityDefinition, ...]) -> tuple[str, float]:
    executable = Path(os.environ["P7_CODEX_EXECUTABLE"])
    codex_home = Path(os.environ["CODEX_HOME"])
    engine = CodexDecisionEngine(
        CodexAgentSettings(
            executable=executable,
            codex_home=codex_home,
            turn_timeout_seconds=180,
        )
    )
    started = time.monotonic()
    decision = await engine.next_decision(
        message=(
            "Call the available read-only capability bulk.tool_119 exactly once with an "
            "empty arguments object. Do not answer without selecting it."
        ),
        conversation_summary="",
        context=CapabilityContext(env=object(), turn_id="p7-real-disclosure"),
        reasoning_capabilities=catalog,
        planning_capabilities=(),
        working_items=(
            {
                "kind": "host_task_plan_state",
                "source": "host",
                "data": {
                    "current_revision": 0,
                    "next_revision": 1,
                    "allowed_revision_kinds": ["initial"],
                    "minimum_initial_steps": 2,
                    "task_plan_available": False,
                },
            },
        ),
        remaining_budgets={"provider_decisions": 1, "reasoning_calls": 1},
    )
    elapsed_ms = round((time.monotonic() - started) * 1000, 3)
    if decision.kind != "reasoning_capability_call":
        raise AssertionError(f"selection_kind_invalid:{decision.kind}")
    if decision.capability != "bulk.tool_119":
        raise AssertionError(f"selection_name_invalid:{decision.capability}")
    if decision.arguments != {}:
        raise AssertionError("selection_arguments_invalid")
    return decision.capability, elapsed_ms


async def main() -> None:
    available = tuple(definition(index) for index in range(120))
    eager_name, eager_ms = await select(available)
    lazy_catalog = (available[0], available[50], available[119])
    lazy_name, lazy_ms = await select(lazy_catalog)
    assert eager_name == lazy_name == "bulk.tool_119"
    assert eager_ms < 180_000 and lazy_ms < 180_000
    print(
        json.dumps(
            {
                "catalog_size": 120,
                "eager_latency_ms": eager_ms,
                "event": "p7_real_disclosure_completed",
                "lazy_latency_ms": lazy_ms,
                "quality_equal": True,
                "result": "PASS",
                "selected_capability": eager_name,
            },
            sort_keys=True,
        )
    )


asyncio.run(main())
