# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models


class HrShiftCoverageGap(models.Model):
    _inherit = "hr.shift.coverage.gap"

    def action_open_split_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Split shift"),
            "res_model": "hr.shift.split.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_gap_id": self.id},
        }
