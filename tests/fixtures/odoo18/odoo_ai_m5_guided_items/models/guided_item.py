from odoo import fields, models


class OdooAiM5GuidedItem(models.Model):
    _name = "odoo.ai.m5.guided.item"
    _description = "M5 Guided Item"
    _order = "name, id"

    name = fields.Char(required=True)
    state = fields.Selection(
        [("open", "Open"), ("done", "Done")],
        default="open",
        required=True,
    )
    guide_code = fields.Char(required=True)
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
