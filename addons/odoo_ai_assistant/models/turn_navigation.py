"""Persist host-resolved navigation references separately from Assistant prose."""

from __future__ import annotations

import json

from odoo import SUPERUSER_ID, fields, models

from ..runtime.capabilities.executor import _public_navigation_references

_MAX_FINAL_REFERENCES = 12


class AssistantTurnNavigationReferences(models.Model):
    _inherit = "odoo.ai.turn"

    public_reference_payload = fields.Json(readonly=True, copy=False)

    def _capture_public_navigation_references(self, working_items):
        """Extract only validated ``odoo.resolve_navigation`` results from host transcript items."""

        self.ensure_one()
        collected = []
        for item in working_items or ():
            kind = getattr(item, "kind", None)
            data = getattr(item, "data", None)
            if kind is None and isinstance(item, dict):
                kind = item.get("kind")
                data = item.get("data")
            if kind != "capability_result" or not isinstance(data, dict):
                continue
            if data.get("capability") != "odoo.resolve_navigation":
                continue
            result = data.get("result")
            if not isinstance(result, dict):
                continue
            raw = result.get("references")
            validated = _public_navigation_references(raw)
            if raw is not None and validated is None:
                continue
            collected.extend(validated or [])

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
