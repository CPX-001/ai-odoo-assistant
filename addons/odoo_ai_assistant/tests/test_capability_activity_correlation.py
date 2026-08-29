import asyncio
import re

from odoo.tests.common import TransactionCase

from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityError,
    CapabilityExecutor,
    CapabilityExposure,
    CapabilityRegistry,
    CapabilityRisk,
)

_ACTIVITY_ID = re.compile(r"^activity:v1:[0-9a-f]{32}$")
_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


class TestCapabilityActivityCorrelation(TransactionCase):
    def _executor(self, handler):
        events = []

        def sink(event_type, title, payload):
            events.append((event_type, title, dict(payload)))

        definition = CapabilityDefinition(
            name="test.activity_probe",
            title="Activity probe",
            description="Exercise semantic activity correlation.",
            input_schema=_SCHEMA,
            output_schema=_SCHEMA,
            risk=CapabilityRisk.READ,
            effect=CapabilityEffect.READ_ONLY,
            exposure=CapabilityExposure.REASONING,
            handler=handler,
            max_calls=4,
        )
        context = CapabilityContext(
            env=self.env(user=self.env.user, su=False),
            turn_id="activity-correlation-test",
            event_sink=sink,
        )
        executor = CapabilityExecutor(
            CapabilityRegistry([definition]),
            context,
            config=CapabilityConfigResolver(),
        )
        return executor, events

    def test_started_and_completed_share_one_host_activity_id(self):
        executor, events = self._executor(lambda _context, _payload: {})
        asyncio.run(executor.execute("test.activity_probe", {}))
        lifecycle = [
            item for item in events if item[0] in {"tool.started", "tool.completed"}
        ]
        self.assertEqual([item[0] for item in lifecycle], ["tool.started", "tool.completed"])
        started_id = lifecycle[0][2].get("activity_id")
        self.assertRegex(started_id, _ACTIVITY_ID)
        self.assertEqual(lifecycle[1][2].get("activity_id"), started_id)

    def test_independent_calls_never_merge_by_capability_name(self):
        executor, events = self._executor(lambda _context, _payload: {})
        asyncio.run(executor.execute("test.activity_probe", {}))
        asyncio.run(executor.execute("test.activity_probe", {}))
        ids = [
            payload["activity_id"]
            for event_type, _title, payload in events
            if event_type == "tool.started"
        ]
        self.assertEqual(len(ids), 2)
        self.assertNotEqual(ids[0], ids[1])

    def test_failure_reuses_the_started_activity_id(self):
        def fail(_context, _payload):
            raise CapabilityError("activity_probe_failed")

        executor, events = self._executor(fail)
        with self.assertRaises(CapabilityError):
            asyncio.run(executor.execute("test.activity_probe", {}))
        lifecycle = [
            item for item in events if item[0] in {"tool.started", "tool.failed"}
        ]
        self.assertEqual([item[0] for item in lifecycle], ["tool.started", "tool.failed"])
        self.assertEqual(lifecycle[0][2]["activity_id"], lifecycle[1][2]["activity_id"])
        self.assertEqual(lifecycle[1][2]["code"], "activity_probe_failed")
