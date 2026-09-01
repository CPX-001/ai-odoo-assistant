"""Normalize legacy nullable autonomy overrides before enforcing the model contract."""

from odoo.tools import sql


def migrate(cr, version):
    del version
    if not sql.column_exists(
        cr,
        "odoo_ai_chat_policy",
        "autonomy_override_active",
    ):
        return
    cr.execute(
        """
        UPDATE odoo_ai_chat_policy
           SET autonomy_override_active = FALSE
         WHERE autonomy_override_active IS NULL
        """
    )
