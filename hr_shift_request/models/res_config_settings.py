# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    swap_auto_approve_hours = fields.Float(
        related="company_id.swap_auto_approve_hours",
        readonly=False,
    )
