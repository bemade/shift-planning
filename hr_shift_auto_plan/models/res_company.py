# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    auto_plan_continuity_days = fields.Integer(
        string="Auto-Plan Continuity Cap (Days)",
        default=5,
        help="The automatic planner chains the same shift on an employee "
        "up to this many days a week. Shorter chains spread the week "
        "more evenly and leave room for the weekend; longer chains "
        "favor schedule stability.",
    )
