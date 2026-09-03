"""Short-TTL Odoo-owned journal for verified Assistant effects and recovery certainty."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import ClassVar
from uuid import UUID

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import ValidationError

_MAX_ROWS_PER_TURN = 8
_MAX_PAYLOAD_BYTES = 64 * 1024
_RETENTION_DAYS = 7
_CLEANUP_LIMIT = 500
_CLASSIFICATIONS = frozenset(
    {"none", "reversible", "reconstructable", "irreversible", "external_or_unknown"}
)
_RECOVERY_MODES = frozenset({"odoo_atomic", "segmented", "external"})


class EffectJournalError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AssistantEffectJournal(models.Model):
    _name = "odoo.ai.effect.journal"
    _description = "Odoo AI Assistant Effect Journal"
    _order = "id desc"

    turn_id = fields.Many2one(
        "odoo.ai.turn",
        required=True,
        readonly=True,
        ondelete="cascade",
        index=True,
    )
    turn_uuid = fields.Char(required=True, readonly=True, index=True, size=64)
    user_id = fields.Many2one("res.users", required=True, readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True, index=True)
    unit_id = fields.Char(required=True, readonly=True, size=64)
    step_id = fields.Char(required=True, readonly=True, size=256)
    capability = fields.Char(required=True, readonly=True, size=160)
    capability_version = fields.Char(required=True, readonly=True, size=32)
    recovery_mode = fields.Selection(
        [
            ("odoo_atomic", "Odoo atomic"),
            ("segmented", "Segmented durable"),
            ("external", "External / non-transactional"),
        ],
        required=True,
        readonly=True,
        index=True,
    )
    classification = fields.Selection(
        [
            ("none", "Not journalled"),
            ("reversible", "Reversible"),
            ("reconstructable", "Reconstructable"),
            ("irreversible", "Irreversible"),
            ("external_or_unknown", "External or unknown"),
        ],
        required=True,
        readonly=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("prepared", "Prepared"),
            ("executing", "Executing"),
            ("verified", "Verified"),
            ("skipped", "Skipped by dependency outcome"),
            ("rolled_back", "Rolled back"),
            ("uncertain", "Uncertain"),
            ("reverted", "Reverted"),
        ],
        required=True,
        readonly=True,
        default="prepared",
        index=True,
    )
    before_payload = fields.Json(required=True, readonly=True, copy=False, default=dict)
    after_payload = fields.Json(readonly=True, copy=False, default=dict)
    receipt_payload = fields.Json(readonly=True, copy=False, default=dict)
    expires_at = fields.Datetime(required=True, readonly=True, index=True)

    _sql_constraints: ClassVar[list[tuple[str, str, str]]] = [
        (
            "effect_journal_turn_step_unique",
            "unique(turn_id, step_id)",
            "Assistant effect journal step identity must be unique.",
        )
    ]

    @api.model
    def _sync_plan(self, turn, plan):
        """Create/update bounded journal rows from one host-validated plan snapshot."""

        if not turn or not isinstance(plan, dict) or plan.get("format_version") != 3:
            raise EffectJournalError("effect_journal_plan_invalid")
        steps = plan.get("steps")
        units = plan.get("recovery_units")
        if (
            not isinstance(steps, list)
            or not 1 <= len(steps) <= _MAX_ROWS_PER_TURN
            or not isinstance(units, list)
            or not units
        ):
            raise EffectJournalError("effect_journal_plan_invalid")
        unit_by_id = {}
        for unit in units:
            if (
                not isinstance(unit, dict)
                or unit.get("mode") not in _RECOVERY_MODES
                or unit.get("state") not in {"prepared", "executing", "completed"}
                or not isinstance(unit.get("unit_id"), str)
            ):
                raise EffectJournalError("effect_journal_plan_invalid")
            unit_by_id[unit["unit_id"]] = unit

        existing = {
            row.step_id: row
            for row in self.with_user(SUPERUSER_ID).search([("turn_id", "=", turn.id)])
            if row.state not in {"rolled_back", "reverted"}
        }
        expires_at = fields.Datetime.now() + timedelta(days=_RETENTION_DAYS)
        seen = set()
        for step in steps:
            values = _row_values(turn, step, unit_by_id, expires_at)
            step_id = values["step_id"]
            if step_id in seen:
                raise EffectJournalError("effect_journal_plan_invalid")
            seen.add(step_id)
            row = existing.get(step_id)
            if not row:
                self.with_user(SUPERUSER_ID).create(values)
                continue
            _validate_binding(row, values)
            updates = _row_updates(row, values)
            if updates:
                row.with_user(SUPERUSER_ID).write(updates)
        if set(existing) - seen:
            raise EffectJournalError("effect_journal_plan_invalid")
        return True

    @api.model
    def _mark_turn_failure(self, turn):
        """Classify an interrupted in-flight recovery unit after worker transaction rollback."""

        rows = self.with_user(SUPERUSER_ID).search([("turn_id", "=", turn.id)])
        if not rows:
            return
        envelope = turn.capability_plan_payload
        plan = envelope.get("plan") if isinstance(envelope, dict) else None
        if not isinstance(plan, dict):
            rows.filtered(lambda row: row.state == "executing").write({"state": "uncertain"})
            return
        units = plan.get("recovery_units")
        if not isinstance(units, list):
            rows.filtered(lambda row: row.state == "executing").write({"state": "uncertain"})
            return
        by_unit = {
            unit.get("unit_id"): unit
            for unit in units
            if isinstance(unit, dict) and isinstance(unit.get("unit_id"), str)
        }
        for row in rows:
            if row.state in {"verified", "skipped", "reverted"}:
                continue
            unit = by_unit.get(row.unit_id)
            if not isinstance(unit, dict):
                if row.state == "executing":
                    row.write({"state": "uncertain"})
                continue
            unit_state = unit.get("state")
            mode = unit.get("mode")
            if unit_state == "completed":
                if row.state != "verified":
                    row.write({"state": "uncertain"})
            elif unit_state == "executing" or (
                unit_state == "prepared" and row.state == "executing"
            ):
                row.write(
                    {"state": "uncertain" if mode == "external" else "rolled_back"}
                )

    @api.model
    def _mark_reverted(self, turn):
        rows = self.with_user(SUPERUSER_ID).search(
            [
                ("turn_id", "=", turn.id),
                ("classification", "=", "reversible"),
                ("state", "=", "verified"),
            ]
        )
        if rows:
            rows.write({"state": "reverted"})

    @api.model
    def _all_turn_effects_rolled_back(self, turn):
        """Return true only when the durable journal proves the whole effect rolled back."""

        rows = self.with_user(SUPERUSER_ID).search([("turn_id", "=", turn.id)])
        return bool(rows) and all(
            row.state in {"rolled_back", "skipped"} for row in rows
        )

    @api.model
    def _cron_cleanup_effect_journal(self):
        expired = self.with_user(SUPERUSER_ID).search(
            [("expires_at", "<", fields.Datetime.now())],
            limit=_CLEANUP_LIMIT,
            order="expires_at, id",
        )
        if expired:
            expired.unlink()

    @api.model
    def _browser_rows(self, turn, *, limit=20):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise EffectJournalError("effect_journal_limit_invalid")
        rows = self.with_user(SUPERUSER_ID).search(
            [("turn_id", "=", turn.id)],
            order="id",
            limit=limit,
        )
        return [_browser_row(row) for row in rows]


class AssistantEffectJournalTurn(models.Model):
    _inherit = "odoo.ai.turn"

    @api.model
    def effect_journal_for_current_user(self, turn_uuid, limit=20):
        turn = self._owned_turn(_canonical_uuid(turn_uuid))
        entries = self.env["odoo.ai.effect.journal"]._browser_rows(turn, limit=limit)
        return {
            "ok": True,
            "turn_id": turn.turn_uuid,
            "conversation_id": (
                turn.conversation_id.conversation_uuid if turn.conversation_id else None
            ),
            "retention_days": _RETENTION_DAYS,
            "entries": entries,
        }

    def write(self, vals):
        result = super().write(vals)
        if not isinstance(vals, dict) or not self:
            return result
        terminal = vals.get("state")
        if terminal in {"failed", "recovery_required", "cancelled"}:
            for turn in self:
                if turn.write_barrier:
                    self.env["odoo.ai.effect.journal"].with_user(
                        SUPERUSER_ID
                    )._mark_turn_failure(turn)
        return result


def _row_values(turn, step, unit_by_id, expires_at):
    if not isinstance(step, dict):
        raise EffectJournalError("effect_journal_plan_invalid")
    step_id = step.get("step_id")
    unit_id = step.get("recovery_unit_id")
    capability = step.get("capability")
    version = step.get("version")
    recovery_mode = step.get("recovery_mode")
    classification = step.get("journal_classification")
    if (
        not isinstance(step_id, str)
        or not isinstance(unit_id, str)
        or unit_id not in unit_by_id
        or not isinstance(capability, str)
        or not isinstance(version, str)
        or recovery_mode not in _RECOVERY_MODES
        or classification not in _CLASSIFICATIONS
    ):
        raise EffectJournalError("effect_journal_plan_invalid")
    if unit_by_id[unit_id].get("mode") != recovery_mode:
        raise EffectJournalError("effect_journal_plan_invalid")
    before = _before_payload(step)
    after = _after_payload(step)
    receipt = _receipt_payload(step)
    unit_state = unit_by_id[unit_id].get("state")
    step_state = step.get("state")
    if step_state == "completed":
        state = "verified"
    elif step_state == "skipped":
        _validate_skipped_step_payload(step)
        state = "skipped"
    elif unit_state == "executing":
        state = "executing"
    else:
        state = "prepared"
    return {
        "turn_id": turn.id,
        "turn_uuid": turn.turn_uuid,
        "user_id": turn.user_id.id,
        "company_id": turn.company_id.id,
        "unit_id": unit_id,
        "step_id": step_id,
        "capability": capability,
        "capability_version": version,
        "recovery_mode": recovery_mode,
        "classification": classification,
        "state": state,
        "before_payload": _bounded_payload(before),
        "after_payload": _bounded_payload(after),
        "receipt_payload": _bounded_payload(receipt),
        "expires_at": expires_at,
    }


def _row_updates(row, values):
    updates = {"expires_at": values["expires_at"]}
    target_state = values["state"]
    if row.state == "reverted":
        target_state = "reverted"
    elif row.state == "verified" and target_state != "verified":
        target_state = "verified"
    elif row.state == "skipped" and target_state != "skipped":
        target_state = "skipped"
    if row.state != target_state:
        updates["state"] = target_state
    for field_name in ("after_payload", "receipt_payload"):
        if values[field_name] and getattr(row, field_name) != values[field_name]:
            updates[field_name] = values[field_name]
    return updates


def _validate_binding(row, values):
    for field_name in (
        "turn_uuid",
        "user_id",
        "company_id",
        "unit_id",
        "step_id",
        "capability",
        "capability_version",
        "recovery_mode",
        "classification",
        "before_payload",
    ):
        current = getattr(row, field_name)
        expected = values[field_name]
        if hasattr(current, "id"):
            current = current.id
        if current != expected:
            raise EffectJournalError("effect_journal_binding_mismatch")


def _before_payload(step):
    preview = step.get("preview")
    if not isinstance(preview, dict):
        raise EffectJournalError("effect_journal_plan_invalid")
    selected = {}
    for key in (
        "operation",
        "model",
        "record_id",
        "display_name",
        "changes",
        "before_active",
        "after_active",
        "values",
        "state",
        "expected_states",
        "reconstruction",
    ):
        if key in preview:
            selected[key] = preview[key]
    return {
        "precondition_fingerprint": step.get("precondition_fingerprint"),
        "binding_fingerprint": step.get("binding_fingerprint"),
        "preview": selected,
    }


def _after_payload(step):
    result = step.get("result")
    verification = step.get("verification")
    if result is None and verification is None:
        return {}
    if not isinstance(result, dict) or not isinstance(verification, dict):
        raise EffectJournalError("effect_journal_plan_invalid")
    return {"result": dict(result), "verification": dict(verification)}


def _receipt_payload(step):
    result = step.get("result")
    verification = step.get("verification")
    if not isinstance(result, dict) or not isinstance(verification, dict):
        return {}
    return {
        "verified": True,
        "step_state": step.get("state"),
        "outcome": result.get("outcome"),
        "capability": step.get("capability"),
        "step_id": step.get("step_id"),
        "record_model": result.get("model"),
        "record_id": result.get("record_id"),
        "verification": dict(verification),
    }


def _validate_skipped_step_payload(step):
    result = step.get("result")
    verification = step.get("verification")
    dependencies = result.get("dependencies") if isinstance(result, dict) else None
    if not (
        isinstance(result, dict)
        and set(result) == {"outcome", "reason", "executed", "dependencies"}
        and result.get("outcome") == "skipped"
        and result.get("reason") == "dependency_incomplete"
        and result.get("executed") is False
        and isinstance(dependencies, list)
        and bool(dependencies)
        and len(dependencies) <= 5
        and all(
            isinstance(item, dict)
            and set(item) == {"step_id", "outcome"}
            and isinstance(item.get("step_id"), str)
            and item.get("outcome") in {"partial", "blocked", "skipped"}
            for item in dependencies
        )
        and verification == {"verified": True, **result}
    ):
        raise EffectJournalError("effect_journal_plan_invalid")


def _bounded_payload(value):
    if not isinstance(value, dict):
        raise EffectJournalError("effect_journal_payload_invalid")
    try:
        raw = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise EffectJournalError("effect_journal_payload_invalid") from None
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise EffectJournalError("effect_journal_payload_too_large")
    return value


def _browser_row(row):
    target = {}
    for payload in (row.receipt_payload, row.after_payload, row.before_payload):
        if not isinstance(payload, dict):
            continue
        candidates = [payload]
        for key in ("result", "preview"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                candidates.append(nested)
        for candidate in candidates:
            model = candidate.get("record_model") or candidate.get("model")
            record_id = candidate.get("record_id")
            if isinstance(model, str) and type(record_id) is int and record_id > 0:
                target = {"model": model, "record_id": record_id}
                break
        if target:
            break
    return {
        "step_id": row.step_id,
        "unit_id": row.unit_id,
        "capability": row.capability,
        "capability_version": row.capability_version,
        "recovery_mode": row.recovery_mode,
        "classification": row.classification,
        "state": row.state,
        "reversible": row.classification == "reversible",
        "reconstructable": row.classification == "reconstructable",
        "target": target or None,
        "created_at": fields.Datetime.to_string(row.create_date) if row.create_date else None,
        "expires_at": fields.Datetime.to_string(row.expires_at) if row.expires_at else None,
    }


def _canonical_uuid(value):
    if not isinstance(value, str):
        raise ValidationError("Invalid Assistant turn id")
    try:
        parsed = str(UUID(value))
    except ValueError as error:
        raise ValidationError("Invalid Assistant turn id") from error
    if parsed != value:
        raise ValidationError("Invalid Assistant turn id")
    return parsed
