from odoo import fields, models


class OdooAiM6ActionItem(models.Model):
    _name = "odoo.ai.m6.action.item"
    _description = "M6 Action Item"
    _order = "name, id"

    name = fields.Char(required=True)
    fixture_key = fields.Char(required=True, readonly=True, index=True)
    reference = fields.Char(required=True)
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
