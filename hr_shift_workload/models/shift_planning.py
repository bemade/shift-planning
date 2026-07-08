# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models


class ShiftPlanningShift(models.Model):
    _inherit = "hr.shift.planning.shift"

    planned_hours = fields.Float(
        compute="_compute_workload",
        store=True,
        help="Hours assigned to this employee over the planning week.",
    )
    allocated_hours = fields.Float(
        compute="_compute_workload",
        store=True,
        help="Weekly hours of the employee's working schedule.",
    )
    overtime = fields.Boolean(
        compute="_compute_workload",
        store=True,
        help="Planned hours exceed the employee's weekly schedule.",
    )

    @api.depends(
        "line_ids.duration_hours",
        "line_ids.state",
        "employee_id.resource_calendar_id.attendance_ids",
    )
    def _compute_workload(self):
        for shift in self:
            planned = sum(
                # hr_shift computes a negative duration for shifts
                # crossing midnight: normalize to the real elapsed time.
                duration if duration >= 0 else duration + 24
                for duration in shift.line_ids.filtered(
                    lambda line: line.state == "assigned"
                ).mapped("duration_hours")
            )
            attendances = shift.employee_id.resource_calendar_id.attendance_ids
            allocated = sum(
                attendance.hour_to - attendance.hour_from for attendance in attendances
            )
            shift.planned_hours = planned
            shift.allocated_hours = allocated
            shift.overtime = allocated > 0 and planned > allocated


class ShiftPlanning(models.Model):
    _inherit = "hr.shift.planning"

    overtime_count = fields.Integer(compute="_compute_overtime_count")

    def _compute_overtime_count(self):
        for planning in self:
            planning.overtime_count = len(planning.shift_ids.filtered("overtime"))

    def action_view_workload(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Workload for %(planning)s", planning=self.display_name),
            "res_model": "hr.shift.planning.shift",
            "view_mode": "list",
            "views": [
                (
                    self.env.ref("hr_shift_workload.shift_workload_tree").id,
                    "list",
                )
            ],
            "domain": [("planning_id", "=", self.id)],
        }
