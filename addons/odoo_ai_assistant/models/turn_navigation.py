"""Persist host-resolved navigation references separately from Assistant prose."""

from __future__ import annotations

import json

from odoo import SUPERUSER_ID, fields, models
from odoo.exceptions import AccessError, MissingError

from ..runtime.capabilities.executor import _public_navigation_references

_MAX_FINAL_REFERENCES = 12


class AssistantTurnNavigationReferences(models.Model):
    _inherit = "odoo.ai.turn"

    public_reference_payload = fields.Json(readonly=True, copy=False)

    def _capture_public_navigation_references(self, working_items):
        """Extract host-resolved navigation and verified record references."""

        self.ensure_one()
        collected = []
        for item in working_items or ():
            kind = getattr(item, "kind", None)
            data = getattr(item, "data", None)
            if kind is None and isinstance(item, dict):
                kind = item.get("kind")
                data = item.get("data")
            if not isinstance(data, dict):
                continue
            if kind == "capability_result" and data.get("capability") == "odoo.resolve_navigation":
                result = data.get("result")
                if not isinstance(result, dict):
                    continue
                raw = result.get("references")
                validated = _public_navigation_references(raw)
                if raw is not None and validated is None:
                    continue
                collected.extend(validated or [])
            elif kind == "verified_effect_receipt":
                collected.extend(self._verified_record_references(data))

        deduped = []
        seen = set()
        for reference in collected:
            key = json.dumps(reference, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(reference)
        selected = deduped[-_MAX_FINAL_REFERENCES:]
        self.with_user(SUPERUSER_ID).write(
            {"public_reference_payload": selected or False}
        )
        return selected

    def _verified_record_references(self, receipt):
        """Project only records proven by a verified receipt under the effective user."""

        self.ensure_one()
        if receipt.get("verified") is not True or not isinstance(receipt.get("steps"), list):
            return []
        allowed_companies = list(self.allowed_company_ids or [self.company_id.id])
        result = []
        for step in receipt["steps"][:_MAX_FINAL_REFERENCES]:
            effect = step.get("result") if isinstance(step, dict) else None
            model = effect.get("model") if isinstance(effect, dict) else None
            record_id = effect.get("record_id") if isinstance(effect, dict) else None
            if not isinstance(model, str) or model not in self.env:
                continue
            if type(record_id) is not int or record_id <= 0:
                continue
            try:
                records = self.env[model].with_user(self.user_id).with_context(
                    allowed_company_ids=allowed_companies
                )
                record = records.browse(record_id).exists()
                if not record or record.id != record_id:
                    continue
                record.check_access("read")
                label = " ".join(str(record.display_name or f"#{record_id}").split())[:160]
            except (AccessError, MissingError, KeyError):
                continue
            result.append(
                {
                    "kind": "odoo_record",
                    "model": model,
                    "record_id": record_id,
                    "label": label,
                }
            )
        return result


class EmbeddedAssistantNavigationResponse(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    def _read_only_response(self, turn, result, policy):
        response = super()._read_only_response(turn, result, policy)
        response["references"] = list(turn.public_reference_payload or [])
        return response

    def _plan_response(self, turn, envelope, policy, *, completed=False):
        response = super()._plan_response(turn, envelope, policy, completed=completed)
        response["references"] = list(turn.public_reference_payload or [])
        return response
