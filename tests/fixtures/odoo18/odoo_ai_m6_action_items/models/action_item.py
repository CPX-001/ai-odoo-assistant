from uuid import uuid4

from odoo import fields, models


class OdooAiM6ActionItem(models.Model):
    _name = "odoo.ai.m6.action.item"
    _description = "M6 Action Item"
    _order = "name, id"

    name = fields.Char(required=True)
    fixture_key = fields.Char(
        default=lambda _self: f"M6-created-{uuid4()}",
        required=True,
        readonly=True,
        index=True,
    )
    reference = fields.Char(default="M6-CREATED-DEFAULT", required=True)
    note = fields.Text()
    write_count = fields.Integer(default=0, readonly=True)
    owner_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    def write(self, values):
        tracked = set(values).intersection({"name", "reference", "note"})
        if tracked and "write_count" not in values:
            values = {**values, "write_count": self.write_count + 1}
        return super().write(values)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    m6_confirm_count = fields.Integer(default=0, readonly=True, copy=False)

    def action_confirm(self):
        result = super().action_confirm()
        for order in self:
            order.m6_confirm_count += 1
        return result
