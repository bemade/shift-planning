# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    swap_auto_approve_hours = fields.Float(
        string="Swap Auto-Approval Window (Hours)",
        default=0,
        help="When the offered shift starts within this many hours, a swap "
        "accepted by the colleague is applied immediately without waiting "
        "for the manager's approval — an urgent slot must not stay empty "
        "for lack of a confirmation. Set to 0 to always require the "
        "manager's approval.",
    )
