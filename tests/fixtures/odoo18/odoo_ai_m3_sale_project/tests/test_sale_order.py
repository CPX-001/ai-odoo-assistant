from odoo.tests import TransactionCase, tagged

from ..models.sale_order import DIAGNOSTIC_ORDER_REFERENCE


@tagged("post_install", "-at_install")
class TestM3SaleProjectFixture(TransactionCase):
    def test_visible_condition_creates_and_updates_one_task(self):
        partner = self.env["res.partner"].create({"name": "M3 Fixture Customer"})
        updated_order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "client_order_ref": DIAGNOSTIC_ORDER_REFERENCE,
            }
        )
        updated_name = f"M3 diagnostic task for {updated_order.name}"
        existing = self.env["project.task"].create(
            {"name": updated_name, "description": "Before confirmation"}
        )
        created_order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "client_order_ref": DIAGNOSTIC_ORDER_REFERENCE,
            }
        )

        (updated_order | created_order).action_confirm()

        updated_tasks = self.env["project.task"].search(
            [("name", "=", updated_name)]
        )
        created_tasks = self.env["project.task"].search(
            [("name", "=", f"M3 diagnostic task for {created_order.name}")]
        )
        self.assertEqual(updated_tasks, existing)
        self.assertEqual(len(created_tasks), 1)
        self.assertIn("visible M3 action_confirm", existing.description)
        self.assertIn("visible M3 action_confirm", created_tasks.description)
