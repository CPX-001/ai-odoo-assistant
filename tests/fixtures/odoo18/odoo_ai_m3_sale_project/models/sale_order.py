from odoo import models

DIAGNOSTIC_ORDER_REFERENCE = "ODOO-AI-M3-CREATE-TASK"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        result = super().action_confirm()
        for order in self:
            if order.client_order_ref != DIAGNOSTIC_ORDER_REFERENCE:
                continue
            task_name = f"M3 diagnostic task for {order.name}"
            task = self.env["project.task"].search(
                [("name", "=", task_name)], limit=1
            )
            values = {
                "name": task_name,
                "description": (
                    "Created by the visible M3 action_confirm fixture condition."
                ),
            }
            if task:
                task.write(values)
            else:
                self.env["project.task"].create(values)
        return result
