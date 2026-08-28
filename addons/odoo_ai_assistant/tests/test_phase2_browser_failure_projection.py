"""Odoo-side deterministic fixtures for Phase 2 browser failure gates."""
from uuid import uuid4
from odoo import SUPERUSER_ID
from odoo.tests.common import TransactionCase
from ..runtime.agent.failure import FailureEnvelope,failure_envelope_payload
def scenario_failure(name):
    base={"code":"runtime_unavailable","category":"internal","stage":"runtime","component":"queue","retryability":"never","effect_state":"none","user_action":"review","safe_summary":"Fallo controlado de validación.","safe_details":{},"diagnostic_id":f"diag-p2real-{name}-0001","provider_code":None}
    routes={"auth":{"code":"codex_turn_failed","category":"authentication","stage":"provider","component":"codex","retryability":"after_change","user_action":"reconnect","provider_code":"unauthorized"},"acl":{"code":"access_denied","category":"odoo_access","stage":"capability","component":"odoo","retryability":"after_change","user_action":"request_access"},"timeout_safe":{"code":"engine_timeout","category":"provider_connection","stage":"provider","component":"codex","retryability":"safe","user_action":"retry"},"toolfail":{"code":"capability_execution_failed","category":"capability_execution","stage":"capability","component":"capability","retryability":"never","user_action":"review"},"recovery":{"code":"worker_lost_after_write_barrier","category":"queue_worker","stage":"execution","component":"queue","retryability":"never","effect_state":"unknown","user_action":"review"}}; base.update(routes[name]); return FailureEnvelope(**base)
class TestPhase2BrowserFailureProjection(TransactionCase):
    def _browser(self,name,recovery=False):
        admin=self.env.ref("base.user_admin"); failure=scenario_failure(name); turn=self.env["odoo.ai.turn"].with_user(SUPERUSER_ID).create({"turn_uuid":str(uuid4()),"user_id":admin.id,"company_id":admin.company_id.id,"state":"running","input_message":"Phase 2 deterministic gate fixture","allowed_company_ids":[admin.company_id.id],"attempt_count":1,"max_attempts":1,"write_barrier":recovery}); turn.write({"state":"recovery_required" if recovery else "failed","error_code":failure.code,"failure_payload":failure_envelope_payload(failure)}); return self.env["odoo.ai.turn"].with_user(turn.user_id).status_for_current_user(turn.turn_uuid)
    def test_auth_projection(self):
        status=self._browser("auth"); self.assertEqual(status["failure"]["category"],"authentication"); self.assertEqual(status["failure"]["user_action"],"reconnect"); self.assertEqual(status["error_code"],status["failure"]["code"])
    def test_acl_projection(self):
        status=self._browser("acl"); self.assertEqual(status["failure"]["category"],"odoo_access"); self.assertEqual(status["failure"]["user_action"],"request_access")
    def test_timeout_without_effect_is_retry_safe(self):
        status=self._browser("timeout_safe"); self.assertEqual(status["failure"]["effect_state"],"none"); self.assertEqual(status["failure"]["retryability"],"safe")
    def test_tool_failure_is_distinct(self):
        status=self._browser("toolfail"); self.assertEqual(status["failure"]["category"],"capability_execution"); self.assertEqual(status["failure"]["component"],"capability")
    def test_recovery_after_write_barrier_is_never_blind_retry(self):
        status=self._browser("recovery",True); self.assertEqual(status["state"],"recovery_required"); self.assertEqual(status["failure"]["effect_state"],"unknown"); self.assertEqual(status["failure"]["retryability"],"never"); self.assertEqual(status["failure"]["user_action"],"review")
