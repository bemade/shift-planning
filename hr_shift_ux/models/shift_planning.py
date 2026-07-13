# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from lxml import etree

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

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        """Order the week-grid day columns after the user's first day of
        week (res.lang week_start), like every Odoo calendar."""
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type != "form":
            return result
        lang = self.env["res.lang"]._lang_get(self.env.user.lang or "en_US")
        first_day = (int(lang.week_start or "1") - 1) % 7
        if not first_day:
            return result
        arch = etree.fromstring(result["arch"])
        day_nodes = {
            int(node.get("name")[-1]): node
            for node in arch.iter("field")
            if (node.get("name") or "").startswith("day_code_")
        }
        if len(day_nodes) == 7:
            parent = day_nodes[0].getparent()
            position = parent.index(day_nodes[0])
            for node in day_nodes.values():
                parent.remove(node)
            for offset in range(7):
                parent.insert(position + offset, day_nodes[(first_day + offset) % 7])
            result["arch"] = etree.tostring(arch, encoding="unicode")
        return result

    def action_view_week_days(self):
        """All day shifts of the week, grouped by day then by shift."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "hr_shift.shift_planning_day_detail_action"
        )
        action["domain"] = [("shift_id.planning_id", "=", self.id)]
        action["context"] = {
            "multi_employee_mode": True,
            "group_by": ["day_number", "template_id"],
        }
        action["display_name"] = self.env._(
            "Day view — %(planning)s", planning=self.display_name
        )
        return action


class ShiftPlanningShift(models.Model):
    _inherit = "hr.shift.planning.shift"

    department_id = fields.Many2one(
        related="employee_id.department_id",
        store=True,
        help="Department (house/residence) of the employee.",
    )
    day_code_0 = fields.Char(string="Mon", compute="_compute_day_codes")
    day_code_1 = fields.Char(string="Tue", compute="_compute_day_codes")
    day_code_2 = fields.Char(string="Wed", compute="_compute_day_codes")
    day_code_3 = fields.Char(string="Thu", compute="_compute_day_codes")
    day_code_4 = fields.Char(string="Fri", compute="_compute_day_codes")
    day_code_5 = fields.Char(string="Sat", compute="_compute_day_codes")
    day_code_6 = fields.Char(string="Sun", compute="_compute_day_codes")

    @api.depends("line_ids.template_id", "line_ids.state")
    def _compute_day_codes(self):
        """Short shift code per week day: the first word of the template
        name (J, S, N…), the leave marker, or nothing on a day off.
        Multiple shifts the same day are joined with a plus (Ja+N)."""
        for shift in self:
            codes = {number: [] for number in range(7)}
            for line in shift.line_ids:
                day = int(line.day_number)
                if line.state in ("holiday", "on_leave"):
                    codes[day].append(self.env._("Leave"))
                elif line.template_id:
                    codes[day].append(line.template_id.display_name.split()[0])
            for number in range(7):
                shift[f"day_code_{number}"] = "+".join(codes.get(number, []))
