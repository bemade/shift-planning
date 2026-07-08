# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models


class HrShiftCoverageGap(models.Model):
    _inherit = "hr.shift.coverage.gap"

    def action_launch_cascade(self):
        """Create a cascade for this open slot and open it for review."""
        self.ensure_one()
        cascade = self.env["hr.shift.cascade"].create(
            {
                "planning_id": self.planning_id.id,
                "template_id": self.template_id.id,
                "day_number": self.day_number,
                "rule_id": self.rule_id.id,
            }
        )
        cascade.action_generate_candidates()
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.shift.cascade",
            "res_id": cascade.id,
            "view_mode": "form",
            "views": [(False, "form")],
        }
