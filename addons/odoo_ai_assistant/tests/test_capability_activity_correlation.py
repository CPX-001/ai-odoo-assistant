import asyncio
import re

from odoo.tests.common import TransactionCase

from ..runtime.capabilities import (
    CapabilityActivitySpec,
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityError,
    CapabilityExecutor,
    CapabilityExposure,
    CapabilityPreview,
    CapabilityRegistry,
    CapabilityResult,
    CapabilityRisk,
    CapabilityVerification,
    ExecutionAuthority,
)

_ACTIVITY_ID = re.compile(r"^activity:v1:[0-9a-f]{32}$")
_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


class TestCapabilityActivityCorrelation(TransactionCase):
    def _executor(self, handler, *, activity=None, event_hook=None):
        events = []

        def sink(event_type, title, payload):
            if event_hook is not None:
                event_hook(event_type)
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
            activity=activity,
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

    def test_context_emit_restores_cursor_before_rethrowing_sink_database_error(self):
        def failing_sink(_event_type, _title, _payload):
            self.env.cr.execute("SELECT 1 / 0")

        context = CapabilityContext(
            env=self.env(user=self.env.user, su=False),
            turn_id="direct-context-emit-database-failure",
            event_sink=failing_sink,
        )

        captured = None
        try:
            context.emit("reasoning.failed", "Projection failed", {"safe": True})
        except Exception as error:  # noqa: BLE001 - assert the sink contract directly
            captured = error

        self.assertIsNotNone(captured)
        self.assertEqual(type(captured).__name__, "DivisionByZero")
        self.env.cr.execute("SELECT 42")
        self.assertEqual(self.env.cr.fetchone(), (42,))

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
        semantic = lifecycle[0][2]["semantic"]
        self.assertEqual(semantic["operation"], "odoo.records.query")
        self.assertEqual(semantic["headline_code"], "activity.query.odoo")
        self.assertNotIn("Activity probe", repr(semantic))

    def test_capability_owned_projector_can_describe_non_core_addon_activity(self):
        activity = CapabilityActivitySpec(
            operation="custom.records.inspect",
            headline_code="activity.custom.inspect",
            projector=lambda _context, _payload: {
                "headline_text": "Inspecting custom workflow records",
                "object_label": "Custom workflow",
            },
        )
        executor, events = self._executor(
            lambda _context, _payload: {},
            activity=activity,
        )

        asyncio.run(executor.execute("test.activity_probe", {}))
        started = next(payload for event, _title, payload in events if event == "tool.started")
        semantic = started["semantic"]

        self.assertEqual(semantic["operation"], "custom.records.inspect")
        self.assertEqual(semantic["headline_code"], "activity.custom.inspect")
        self.assertEqual(
            semantic["headline_args"]["headline_text"],
            "Inspecting custom workflow records",
        )
        self.assertEqual(semantic["headline_args"]["object_label"], "Custom workflow")

    def test_activity_projector_failure_never_fails_business_operation(self):
        def fail_projection(_context, _payload):
            raise RuntimeError("presentation-only failure")

        activity = CapabilityActivitySpec(
            operation="custom.records.inspect",
            headline_code="activity.custom.inspect",
            projector=fail_projection,
        )
        executor, events = self._executor(
            lambda _context, _payload: {},
            activity=activity,
        )

        asyncio.run(executor.execute("test.activity_probe", {}))
        completed = next(payload for event, _title, payload in events if event == "tool.completed")

        self.assertEqual(completed["semantic"]["operation"], "custom.records.inspect")
        self.assertEqual(completed["semantic"]["headline_args"], {})

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
        groups = [
            payload["semantic"]["group_key"]
            for event_type, _title, payload in events
            if event_type == "tool.started"
        ]
        self.assertEqual(groups, [None, None])

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

    def test_database_handler_failure_restores_cursor_before_returning_error(self):
        def fail_with_database_error(context, _payload):
            context.env.cr.execute("SELECT 1 / 0")

        def prove_failure_projection_has_a_clean_cursor(event_type):
            if event_type in {"tool.failed", "diagnostic.capability_timing"}:
                self.env.cr.execute("SELECT 7")
                self.assertEqual(self.env.cr.fetchone(), (7,))

        executor, events = self._executor(
            fail_with_database_error,
            event_hook=prove_failure_projection_has_a_clean_cursor,
        )

        captured = None
        try:
            asyncio.run(executor.execute("test.activity_probe", {}))
        except CapabilityError as error:
            captured = error

        self.assertIsNotNone(captured)
        self.assertEqual(captured.code, "capability_handler_failed")
        self.assertEqual(captured.details["stage"], "execute")
        self.assertEqual(captured.details["exception_type"], "DivisionByZero")
        self.env.cr.execute("SELECT 42")
        self.assertEqual(self.env.cr.fetchone(), (42,))
        self.assertEqual(
            [item[0] for item in events],
            ["tool.started", "tool.failed", "diagnostic.capability_timing"],
        )

    def test_provider_error_after_database_failure_keeps_its_bounded_contract(self):
        def reject_after_database_error(context, _payload):
            try:
                context.env.cr.execute("SELECT 1 / 0")
            except Exception as error:
                raise CapabilityError(
                    "action_rejected",
                    details={"failure_kind": "database_constraint"},
                ) from error

        executor, events = self._executor(reject_after_database_error)

        captured = None
        try:
            asyncio.run(executor.execute("test.activity_probe", {}))
        except CapabilityError as error:
            captured = error

        self.assertIsNotNone(captured)
        self.assertEqual(captured.code, "action_rejected")
        self.assertEqual(
            dict(captured.details),
            {"failure_kind": "database_constraint"},
        )
        self.env.cr.execute("SELECT 42")
        self.assertEqual(self.env.cr.fetchone(), (42,))
        failed = next(payload for event, _title, payload in events if event == "tool.failed")
        self.assertEqual(failed["code"], "action_rejected")

    def test_failure_event_database_error_never_masks_the_primary_contract(self):
        def fail(_context, _payload):
            raise CapabilityError("action_rejected", details={"operation": "probe"})

        def fail_public_failure_event(event_type):
            if event_type == "tool.failed":
                self.env.cr.execute("SELECT 1 / 0")

        executor, _events = self._executor(
            fail,
            event_hook=fail_public_failure_event,
        )

        captured = None
        try:
            asyncio.run(executor.execute("test.activity_probe", {}))
        except CapabilityError as error:
            captured = error

        self.assertIsNotNone(captured)
        self.assertEqual(captured.code, "action_rejected")
        self.assertEqual(dict(captured.details), {"operation": "probe"})
        self.env.cr.execute("SELECT 42")
        self.assertEqual(self.env.cr.fetchone(), (42,))

    def test_timing_database_error_cannot_poison_a_successful_call(self):
        def fail_timing_event(event_type):
            if event_type == "diagnostic.capability_timing":
                self.env.cr.execute("SELECT 1 / 0")

        executor, _events = self._executor(
            lambda _context, _payload: {},
            event_hook=fail_timing_event,
        )

        result = asyncio.run(executor.execute("test.activity_probe", {}))

        self.assertEqual(dict(result.data), {})
        self.env.cr.execute("SELECT 42")
        self.assertEqual(self.env.cr.fetchone(), (42,))

    def test_started_and_completed_database_event_failures_are_fail_soft(self):
        fingerprint = f"sha256:{'0' * 64}"
        lifecycle_cases = (
            ("tool.preview.started", "preview"),
            ("tool.preview.completed", "preview"),
            ("tool.started", "execute"),
            ("tool.completed", "execute"),
            ("tool.verify.started", "verify"),
            ("tool.verify.completed", "verify"),
        )
        for failed_event, stage in lifecycle_cases:
            with self.subTest(event=failed_event):
                target = self.env["res.partner"].create(
                    {"name": f"Lifecycle before {failed_event}"}
                )
                attempted_events = []

                def sink(
                    event_type,
                    _title,
                    _payload,
                    attempted_events=attempted_events,
                    failed_event=failed_event,
                ):
                    attempted_events.append(event_type)
                    if event_type == failed_event:
                        self.env.cr.execute("SELECT 1 / 0")

                def execute_handler(
                    context,
                    _payload,
                    target=target,
                    failed_event=failed_event,
                ):
                    record = context.env["res.partner"].browse(target.id)
                    record.write({"name": f"Lifecycle applied {failed_event}"})
                    return {}

                definition = CapabilityDefinition(
                    name="test.lifecycle_database_probe",
                    title="Lifecycle database probe",
                    description="Prove public lifecycle events are non-authoritative.",
                    input_schema=_SCHEMA,
                    output_schema=_SCHEMA,
                    risk=CapabilityRisk.READ,
                    effect=CapabilityEffect.READ_ONLY,
                    exposure=CapabilityExposure.PLAN,
                    handler=execute_handler,
                    preview_handler=lambda _context, _payload: CapabilityPreview(
                        summary={},
                        precondition_fingerprint=fingerprint,
                    ),
                    verify_handler=lambda _context, _payload: CapabilityVerification(
                        verified=True,
                        summary={},
                    ),
                )
                context = CapabilityContext(
                    env=self.env(user=self.env.user, su=False),
                    turn_id=f"lifecycle-event-{stage}",
                    event_sink=sink,
                )
                executor = CapabilityExecutor(
                    CapabilityRegistry([definition]),
                    context,
                    config=CapabilityConfigResolver(),
                )

                if stage == "preview":
                    result = asyncio.run(executor.preview(definition.name, {}))
                    self.assertEqual(dict(result.summary), {})
                elif stage == "execute":
                    result = asyncio.run(
                        executor.execute(
                            definition.name,
                            {},
                            authority=ExecutionAuthority.PLAN,
                            approved=True,
                        )
                    )
                    self.assertEqual(dict(result.data), {})
                    self.assertEqual(target.name, f"Lifecycle applied {failed_event}")
                else:
                    result = asyncio.run(
                        executor.verify(
                            definition.name,
                            {},
                            CapabilityResult(data={}),
                        )
                    )
                    self.assertTrue(result.verified)
                self.assertIn(failed_event, attempted_events)
                self.env.cr.execute("SELECT 42")
                self.assertEqual(self.env.cr.fetchone(), (42,))

    def test_plan_failure_event_database_errors_preserve_primary_contract(self):
        fingerprint = f"sha256:{'0' * 64}"
        cases = (
            ("tool.preview.failed", "preview", "action_rejected"),
            (
                "tool.verify.failed",
                "verify",
                "capability_verification_failed",
            ),
        )
        for failed_event, stage, expected_code in cases:
            with self.subTest(event=failed_event):
                def sink(event_type, _title, _payload, failed_event=failed_event):
                    if event_type == failed_event:
                        self.env.cr.execute("SELECT 1 / 0")

                def preview_handler(_context, _payload, stage=stage):
                    if stage == "preview":
                        raise CapabilityError("action_rejected")
                    return CapabilityPreview(
                        summary={},
                        precondition_fingerprint=fingerprint,
                    )

                definition = CapabilityDefinition(
                    name="test.lifecycle_failure_probe",
                    title="Lifecycle failure probe",
                    description="Prove failure events never replace plan errors.",
                    input_schema=_SCHEMA,
                    output_schema=_SCHEMA,
                    risk=CapabilityRisk.READ,
                    effect=CapabilityEffect.READ_ONLY,
                    exposure=CapabilityExposure.PLAN,
                    handler=lambda _context, _payload: {},
                    preview_handler=preview_handler,
                    verify_handler=lambda _context, _payload, stage=stage: CapabilityVerification(
                        verified=stage != "verify",
                        summary={},
                    ),
                )
                context = CapabilityContext(
                    env=self.env(user=self.env.user, su=False),
                    turn_id=f"lifecycle-failure-{stage}",
                    event_sink=sink,
                )
                executor = CapabilityExecutor(
                    CapabilityRegistry([definition]),
                    context,
                    config=CapabilityConfigResolver(),
                )

                captured = None
                try:
                    if stage == "preview":
                        asyncio.run(executor.preview(definition.name, {}))
                    else:
                        asyncio.run(
                            executor.verify(
                                definition.name,
                                {},
                                CapabilityResult(data={}),
                            )
                        )
                except CapabilityError as error:
                    captured = error
                self.assertIsNotNone(captured)
                self.assertEqual(captured.code, expected_code)
                self.env.cr.execute("SELECT 42")
                self.assertEqual(self.env.cr.fetchone(), (42,))

    def test_invalid_execute_output_rolls_back_writes_and_preserves_caller_state(self):
        target = self.env["res.partner"].create({"name": "Validated target before"})
        caller_record = self.env["res.partner"].create({"name": "Caller before"})
        self.env.flush_all()
        caller_record.name = "Caller pending value"
        self.assertTrue(
            self.env.cache.has_dirty_fields(
                caller_record,
                [caller_record._fields["name"]],
            )
        )

        def mutate_then_return_invalid_output(context, _payload):
            record = context.env["res.partner"].browse(target.id)
            record.write({"name": "Invalid capability mutation"})
            record.flush_recordset(["name"])
            return {"unexpected": True}

        definition = CapabilityDefinition(
            name="test.invalid_output_write_probe",
            title="Invalid output write probe",
            description="Roll back writes when the handler output contract is invalid.",
            input_schema=_SCHEMA,
            output_schema=_SCHEMA,
            risk=CapabilityRisk.READ,
            effect=CapabilityEffect.READ_ONLY,
            exposure=CapabilityExposure.REASONING,
            handler=mutate_then_return_invalid_output,
        )
        context = CapabilityContext(
            env=self.env(user=self.env.user, su=False),
            turn_id="invalid-output-write-probe",
        )
        executor = CapabilityExecutor(
            CapabilityRegistry([definition]),
            context,
            config=CapabilityConfigResolver(),
        )

        captured = None
        try:
            asyncio.run(executor.execute(definition.name, {}))
        except CapabilityError as error:
            captured = error

        self.assertIsNotNone(captured)
        self.assertEqual(captured.code, "capability_output_invalid")
        self.assertEqual(target.name, "Validated target before")
        self.assertEqual(caller_record.name, "Caller pending value")
        self.env.cr.execute(
            "SELECT id, name FROM res_partner WHERE id IN %s ORDER BY id",
            [tuple(sorted((target.id, caller_record.id)))],
        )
        names = dict(self.env.cr.fetchall())
        self.assertEqual(names[target.id], "Validated target before")
        self.assertEqual(names[caller_record.id], "Caller pending value")
        self.env.cr.execute("SELECT 42")
        self.assertEqual(self.env.cr.fetchone(), (42,))

    def test_pending_caller_flush_failure_is_inside_the_outer_savepoint(self):
        anchor = self.env["res.partner"].create({"name": "Flush boundary anchor"})
        module = f"executor_boundary_{anchor.id}"
        first = self.env["ir.model.data"].create(
            {
                "module": module,
                "name": "first",
                "model": "res.partner",
                "res_id": anchor.id,
            }
        )
        second = self.env["ir.model.data"].create(
            {
                "module": module,
                "name": "second",
                "model": "res.partner",
                "res_id": anchor.id,
            }
        )
        self.env.flush_all()
        second.name = "first"
        self.assertTrue(
            self.env.cache.has_dirty_fields(second, [second._fields["name"]])
        )
        handler_called = []

        def handler(_context, _payload):
            handler_called.append(True)
            return {}

        definition = CapabilityDefinition(
            name="test.pending_flush_probe",
            title="Pending flush probe",
            description="Guard the caller-state flush before invoking a capability.",
            input_schema=_SCHEMA,
            output_schema=_SCHEMA,
            risk=CapabilityRisk.READ,
            effect=CapabilityEffect.READ_ONLY,
            exposure=CapabilityExposure.REASONING,
            handler=handler,
        )
        context = CapabilityContext(
            env=self.env(user=self.env.user, su=False),
            turn_id="pending-flush-probe",
        )
        executor = CapabilityExecutor(
            CapabilityRegistry([definition]),
            context,
            config=CapabilityConfigResolver(),
        )

        captured = None
        try:
            asyncio.run(executor.execute(definition.name, {}))
        except CapabilityError as error:
            captured = error

        self.assertIsNotNone(captured)
        self.assertEqual(captured.code, "capability_handler_failed")
        self.assertEqual(captured.details["exception_type"], "UniqueViolation")
        self.assertEqual(handler_called, [])
        self.assertEqual(first.name, "first")
        self.assertEqual(second.name, "second")
        self.env.cr.execute("SELECT 42")
        self.assertEqual(self.env.cr.fetchone(), (42,))

    def test_invalid_preview_and_verify_outputs_roll_back_handler_writes(self):
        fingerprint = f"sha256:{'0' * 64}"
        cases = (
            ("preview", "capability_preview_invalid"),
            ("verify", "capability_verification_failed"),
        )
        for stage, expected_code in cases:
            with self.subTest(stage=stage):
                target = self.env["res.partner"].create(
                    {"name": f"{stage} validation before"}
                )
                self.env.flush_all()

                def mutate(context, target=target, stage=stage):
                    record = context.env["res.partner"].browse(target.id)
                    record.write({"name": f"{stage} invalid mutation"})
                    record.flush_recordset(["name"])

                def preview_handler(context, _payload, stage=stage):
                    mutate(context)
                    if stage == "preview":
                        return {}
                    return CapabilityPreview(
                        summary={},
                        precondition_fingerprint=fingerprint,
                    )

                def verify_handler(context, _payload):
                    mutate(context)
                    return CapabilityVerification(verified=False, summary={})

                definition = CapabilityDefinition(
                    name="test.invalid_plan_output_probe",
                    title="Invalid plan output probe",
                    description="Roll back plan handler writes rejected by output validation.",
                    input_schema=_SCHEMA,
                    output_schema=_SCHEMA,
                    risk=CapabilityRisk.READ,
                    effect=CapabilityEffect.READ_ONLY,
                    exposure=CapabilityExposure.PLAN,
                    handler=lambda _context, _payload: {},
                    preview_handler=preview_handler,
                    verify_handler=verify_handler,
                )
                context = CapabilityContext(
                    env=self.env(user=self.env.user, su=False),
                    turn_id=f"invalid-plan-output-{stage}",
                )
                executor = CapabilityExecutor(
                    CapabilityRegistry([definition]),
                    context,
                    config=CapabilityConfigResolver(),
                )

                captured = None
                try:
                    if stage == "preview":
                        asyncio.run(executor.preview(definition.name, {}))
                    else:
                        asyncio.run(
                            executor.verify(
                                definition.name,
                                {},
                                CapabilityResult(data={}),
                            )
                        )
                except CapabilityError as error:
                    captured = error
                self.assertIsNotNone(captured)
                self.assertEqual(captured.code, expected_code)
                self.assertEqual(target.name, f"{stage} validation before")
                self.env.cr.execute(
                    "SELECT name FROM res_partner WHERE id = %s",
                    [target.id],
                )
                self.assertEqual(self.env.cr.fetchone(), (f"{stage} validation before",))

    def test_preview_and_verify_database_failures_restore_the_shared_cursor(self):
        def fail_with_database_error(context, _payload):
            context.env.cr.execute("SELECT 1 / 0")

        definition = CapabilityDefinition(
            name="test.plan_database_probe",
            title="Plan database probe",
            description="Exercise transaction isolation in every plan lifecycle phase.",
            input_schema=_SCHEMA,
            output_schema=_SCHEMA,
            risk=CapabilityRisk.READ,
            effect=CapabilityEffect.READ_ONLY,
            exposure=CapabilityExposure.PLAN,
            handler=lambda _context, _payload: {},
            preview_handler=fail_with_database_error,
            verify_handler=fail_with_database_error,
        )
        context = CapabilityContext(
            env=self.env(user=self.env.user, su=False),
            turn_id="plan-database-probe-test",
        )
        executor = CapabilityExecutor(
            CapabilityRegistry([definition]),
            context,
            config=CapabilityConfigResolver(),
        )
        invocations = (
            ("preview", lambda: executor.preview(definition.name, {})),
            (
                "verify",
                lambda: executor.verify(
                    definition.name,
                    {},
                    CapabilityResult(data={}),
                ),
            ),
        )

        for stage, invocation in invocations:
            with self.subTest(stage=stage):
                captured = None
                try:
                    asyncio.run(invocation())
                except CapabilityError as error:
                    captured = error
                self.assertIsNotNone(captured)
                self.assertEqual(captured.code, "capability_handler_failed")
                self.assertEqual(captured.details["stage"], stage)
                self.env.cr.execute("SELECT 42")
                self.assertEqual(self.env.cr.fetchone(), (42,))

    def test_database_failure_in_activity_projection_is_transaction_isolated(self):
        def fail_projection(context, _payload):
            context.env.cr.execute("SELECT 1 / 0")

        activity = CapabilityActivitySpec(
            operation="custom.records.inspect",
            headline_code="activity.custom.inspect",
            projector=fail_projection,
        )
        executor, events = self._executor(
            lambda _context, _payload: {},
            activity=activity,
        )

        result = asyncio.run(executor.execute("test.activity_probe", {}))

        self.assertEqual(dict(result.data), {})
        self.env.cr.execute("SELECT 42")
        self.assertEqual(self.env.cr.fetchone(), (42,))
        completed = next(payload for event, _title, payload in events if event == "tool.completed")
        self.assertEqual(completed["semantic"]["headline_args"], {})

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
