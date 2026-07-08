# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models


class HrShiftCoverageGap(models.Model):
    _inherit = "hr.shift.coverage.gap"

    def action_claim(self):
        """Let the current user claim this open slot."""
        self.ensure_one()
        employee = self.env.user.employee_id
        if not employee:
            return False
        claim = self.env["hr.shift.claim"].create(
            {
                "planning_id": self.planning_id.id,
                "template_id": self.template_id.id,
                "day_number": self.day_number,
                "employee_id": employee.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.shift.claim",
            "res_id": claim.id,
            "view_mode": "form",
            "views": [(False, "form")],
        }
