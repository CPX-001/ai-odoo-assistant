"""Opt-in Phase 3 real-environment acceptance harness; excluded from standard tests until eligible."""
from uuid import uuid4
from odoo import SUPERUSER_ID,api
from odoo.modules.registry import Registry
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
@tagged("-standard","phase3_real")
class TestPhase3PublicActivityRealGates(TransactionCase):
    def _turn(self):
        db=self.env.cr.dbname
        with Registry(db).cursor() as cr:
            env=api.Environment(cr,SUPERUSER_ID,{},su=True); admin=env.ref("base.user_admin"); turn=env["odoo.ai.turn"].create({"turn_uuid":str(uuid4()),"user_id":admin.id,"company_id":admin.company_id.id,"state":"running","input_message":"Phase 3 live visibility gate","allowed_company_ids":[admin.company_id.id],"attempt_count":1,"max_attempts":1}); result=(turn.id,turn.turn_uuid,admin.id); cr.commit(); return result
    def _api(self,env):
        append=getattr(env["odoo.ai.turn.event"],"append_public_independent",None); read=getattr(env["odoo.ai.turn"],"public_events_for_current_user",None); self.assertTrue(callable(append) and callable(read),"Phase 3 production public-activity API is not implemented yet; expected before Phase 2 real closeout."); return append,read
    def test_activity_read_is_bounded_and_reconnectable(self):
        tid,tu,uid=self._turn(); append,_=self._api(self.env); append(turn_id=tid,kind="capability.started",phase="capability",status="running",label="Consultando res.partner",resource={"model":"res.partner","record_ids":[],"display_names":[]},capability="odoo.query_records"); model=self.env["odoo.ai.turn"].with_user(uid); first=model.public_events_for_current_user(tu,after_sequence=0); self.assertGreaterEqual(len(first["events"]),1); second=model.public_events_for_current_user(tu,after_sequence=first["last_sequence"]); self.assertEqual(second["events"],[])
    def test_activity_action_has_real_lifecycle_without_arguments_or_results(self):
        tid,tu,uid=self._turn(); append,_=self._api(self.env); append(turn_id=tid,kind="preview.started",phase="preview",status="running",label="Preparando cambio",resource={"model":"res.partner","record_ids":[],"display_names":[]},capability="odoo.record.patch"); events=self.env["odoo.ai.turn"].with_user(uid).public_events_for_current_user(tu,after_sequence=0)["events"]; encoded=repr(events).lower(); self.assertIn("preview.started",encoded); [self.assertNotIn(x,encoded) for x in ("arguments","result_payload","prompt","working_items_payload")]
    def test_live_visibility_uses_second_connection_before_turn_commit(self):
        db=self.env.cr.dbname; tid,tu,uid=self._turn()
        with Registry(db).cursor() as worker_cr:
            worker=api.Environment(worker_cr,SUPERUSER_ID,{},su=True); append,_=self._api(worker); append(turn_id=tid,kind="capability.started",phase="capability",status="running",label="Consultando datos",resource=None,capability="odoo.query_records")
            with Registry(db).cursor() as observer_cr:
                observer=api.Environment(observer_cr,uid,{},su=False); read=getattr(observer["odoo.ai.turn"],"public_events_for_current_user",None); self.assertTrue(callable(read)); observed=read(tu,after_sequence=0); self.assertTrue(any(x.get("kind")=="capability.started" for x in observed["events"]),"No public event visible from second connection before worker transaction commit")
    def test_redaction_rejects_private_reasoning_and_secret_bearing_fields(self):
        tid,tu,uid=self._turn(); append,_=self._api(self.env)
        with self.assertRaises(Exception): append(turn_id=tid,kind="agent.thinking",phase="provider",status="running",label="private reasoning",resource=None,capability=None)
        append(turn_id=tid,kind="provider.connected",phase="provider",status="completed",label="Proveedor conectado",resource=None,capability=None); encoded=repr(self.env["odoo.ai.turn"].with_user(uid).public_events_for_current_user(tu,after_sequence=0)["events"]).lower(); [self.assertNotIn(x,encoded) for x in ("secret","password","token","stderr","stdout","prompt","thinking")]
