# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models


class ShiftPlanning(models.Model):
    _inherit = "hr.shift.planning"

    line_assigned_count = fields.Integer(
        string="Assigned day shifts",
        compute="_compute_line_counts",
        help="Number of day shifts with an employee assigned over the week.",
    )
    line_unassigned_count = fields.Integer(
        string="Open day shifts",
        compute="_compute_line_counts",
        help="Number of day shifts still without an employee over the week.",
    )

    @api.depends("shift_ids.line_ids.state")
    def _compute_line_counts(self):
        for planning in self:
            lines = planning.shift_ids.line_ids
            planning.line_assigned_count = len(
                lines.filtered(lambda line: line.state == "assigned")
            )
            planning.line_unassigned_count = len(
                lines.filtered(lambda line: line.state == "unassigned")
            )


class ShiftPlanningShift(models.Model):
    _inherit = "hr.shift.planning.shift"

    department_id = fields.Many2one(
        related="employee_id.department_id",
        store=True,
        help="Department (house/residence) of the employee.",
    )
