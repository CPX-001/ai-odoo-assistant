from odoo.tests.common import TransactionCase

from ..models.assistant_chat_bridge import _browser_plan_execution
from ..services import AssistantServiceError

PLAN_ID = "32345678-1234-4678-9234-567812345678"


def _plan(state="authorized", step_state="planned"):
    return {
        "plan_id": PLAN_ID,
        "state": state,
        "risk": "high",
        "metadata": {
            "needs_read": False,
            "needs_schema": True,
            "needs_write": True,
            "needs_business_action": False,
            "has_external_effect": False,
            "has_irreversible_effect": False,
            "is_atomic": False,
            "estimated_blast_radius": 100,
        },
        "policy": {
            "confirmation_mode": "risk_based",
            "max_auto_risk": "high",
            "allow_synthetic_data": False,
            "constrained_by": ["user"],
        },
        "goal": "Actualizar un lote validado",
        "assumptions": [],
        "steps": [
            {
                "step_id": "bulk_update",
                "title": "Actualizar lote",
                "state": step_state,
                "risk": "high",
                "effect_scope": "internal_reversible",
                "receipt": None,
            }
        ],
        "requires_confirmation": False,
        "expires_at": None,
    }


class TestAgentPlanRecoveryBridge(TransactionCase):
    def test_recoverable_authorized_status_is_accepted(self):
        result = _browser_plan_execution(
            {
                "answer_markdown": "Recuperación pendiente.",
                "completed_at": None,
                "error_code": "batch_execution_outcome_unknown",
                "plan": _plan(),
            },
            PLAN_ID,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "authorized")
        self.assertEqual(result["plan"]["plan_id"], PLAN_ID)

    def test_plain_authorized_status_cannot_impersonate_recovery(self):
        with self.assertRaises(AssistantServiceError):
            _browser_plan_execution(
                {
                    "answer_markdown": "Autorizado.",
                    "completed_at": None,
                    "error_code": None,
                    "plan": _plan(),
                },
                PLAN_ID,
            )

    def test_partial_step_remains_browser_valid(self):
        result = _browser_plan_execution(
            {
                "answer_markdown": "Resultado parcial.",
                "completed_at": "2026-08-25T02:00:00Z",
                "error_code": "agent_step_partial",
                "plan": _plan(state="partial", step_state="partial"),
            },
            PLAN_ID,
        )

        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["plan"]["steps"][0]["state"], "partial")
