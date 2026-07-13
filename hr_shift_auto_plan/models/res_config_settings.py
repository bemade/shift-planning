# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    auto_plan_continuity_days = fields.Integer(
        related="company_id.auto_plan_continuity_days",
        readonly=False,
    )
