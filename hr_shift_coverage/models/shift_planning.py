# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ShiftPlanning(models.Model):
    _inherit = "hr.shift.planning"

    coverage_gap_ids = fields.One2many(
        comodel_name="hr.shift.coverage.gap",
        inverse_name="planning_id",
    )
    coverage_gap_count = fields.Integer(compute="_compute_coverage_gap_count")

    def _compute_coverage_gap_count(self):
        for planning in self:
            planning.coverage_gap_count = len(planning.coverage_gap_ids)

    def _get_coverage_rules(self):
        return self.env["hr.shift.coverage.rule"].search(
            [("company_id", "in", [False, *self.env.companies.ids])]
        )

    def _update_coverage_gaps(self):
        """Recompute the coverage gaps of these plannings from the active
        coverage rules and the currently assigned shift lines."""
        rules = self._get_coverage_rules()
        for planning in self:
            assigned_lines = planning.shift_ids.line_ids.filtered(
                lambda line: line.state == "assigned" and line.template_id
            )
            gap_vals = []
            for rule in rules:
                for day_number in rule._get_covered_day_numbers():
                    assigned = rule._covering_line_count(assigned_lines, day_number)
                    missing = rule.min_employees - assigned
                    if missing > 0:
                        gap_vals.append(
                            {
                                "planning_id": planning.id,
                                "rule_id": rule.id,
                                "day_number": day_number,
                                "required": rule.min_employees,
                                "assigned": assigned,
                                "missing": missing,
                            }
                        )
            planning.coverage_gap_ids.unlink()
            self.env["hr.shift.coverage.gap"].create(gap_vals)

    def action_check_coverage(self):
        self.ensure_one()
        self._update_coverage_gaps()
        if not self.coverage_gap_ids:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "success",
                    "title": self.env._("Coverage is complete"),
                    "message": self.env._(
                        "Every coverage rule is satisfied for this planning."
                    ),
                    "sticky": False,
                },
            }
        action = self.env["ir.actions.actions"]._for_xml_id(
            "hr_shift_coverage.hr_shift_coverage_gap_action"
        )
        action["domain"] = [("planning_id", "=", self.id)]
        action["display_name"] = self.env._(
            "Coverage gaps for %(planning)s", planning=self.display_name
        )
        return action
