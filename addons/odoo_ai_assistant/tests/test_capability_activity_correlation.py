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

    def test_completed_read_projects_only_revalidated_record_identities(self):
        first = self.env["res.partner"].create({"name": "Semantic Ref A"})
        second = self.env["res.partner"].create({"name": "Semantic Ref B"})
        events = []

        def sink(event_type, title, payload):
            events.append((event_type, title, dict(payload)))

        input_schema = {
            "type": "object",
            "properties": {"model": {"type": "string"}},
            "required": ["model"],
            "additionalProperties": False,
        }
        output_schema = {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "records": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                        "required": ["id"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["model", "records"],
            "additionalProperties": False,
        }
        definition = CapabilityDefinition(
            name="test.reference_probe",
            title="Reference probe",
            description="Return already-readable records for public reference projection.",
            input_schema=input_schema,
            output_schema=output_schema,
            risk=CapabilityRisk.READ,
            effect=CapabilityEffect.READ_ONLY,
            exposure=CapabilityExposure.REASONING,
            handler=lambda _context, _payload: {
                "model": "res.partner",
                "records": [{"id": first.id}, {"id": second.id}],
            },
        )
        context = CapabilityContext(
            env=self.env(user=self.env.user, su=False),
            turn_id="activity-reference-test",
            event_sink=sink,
        )
        executor = CapabilityExecutor(
            CapabilityRegistry([definition]),
            context,
            config=CapabilityConfigResolver(),
        )

        asyncio.run(executor.execute("test.reference_probe", {"model": "res.partner"}))
        started = next(payload for event, _title, payload in events if event == "tool.started")
        completed = next(payload for event, _title, payload in events if event == "tool.completed")

        self.assertNotIn("record_ids", started)
        self.assertEqual(completed["record_ids"], [first.id, second.id])
        self.assertEqual(completed["display_names"], ["Semantic Ref A", "Semantic Ref B"])
        self.assertNotIn("records", completed)

    def test_completed_mutation_can_project_output_model_and_single_record(self):
        partner = self.env["res.partner"].create({"name": "Semantic Mutation Ref"})
        events = []

        def sink(event_type, title, payload):
            events.append((event_type, title, dict(payload)))

        output_schema = {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "record_id": {"type": "integer"},
                "operation": {"type": "string"},
            },
            "required": ["model", "record_id", "operation"],
            "additionalProperties": False,
        }
        definition = CapabilityDefinition(
            name="test.mutation_reference_probe",
            title="Mutation reference probe",
            description="Return one mutation identity for semantic navigation projection.",
            input_schema=_SCHEMA,
            output_schema=output_schema,
            risk=CapabilityRisk.READ,
            effect=CapabilityEffect.READ_ONLY,
            exposure=CapabilityExposure.REASONING,
            handler=lambda _context, _payload: {
                "model": "res.partner",
                "record_id": partner.id,
                "operation": "probe",
            },
        )
        context = CapabilityContext(
            env=self.env(user=self.env.user, su=False),
            turn_id="activity-mutation-reference-test",
            event_sink=sink,
        )
        executor = CapabilityExecutor(
            CapabilityRegistry([definition]),
            context,
            config=CapabilityConfigResolver(),
        )

        asyncio.run(executor.execute("test.mutation_reference_probe", {}))
        completed = next(payload for event, _title, payload in events if event == "tool.completed")

        self.assertEqual(completed["model"], "res.partner")
        self.assertEqual(completed["record_ids"], [partner.id])
        self.assertEqual(completed["display_names"], ["Semantic Mutation Ref"])
        self.assertNotIn("operation", completed)
