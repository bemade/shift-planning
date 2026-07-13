# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models
from odoo.exceptions import UserError


class HrShiftRotationApply(models.TransientModel):
    _name = "hr.shift.rotation.apply"
    _description = "Apply a Shift Rotation"

    rotation_id = fields.Many2one(
        comodel_name="hr.shift.rotation",
        required=True,
    )
    year = fields.Integer(required=True)
    week_from = fields.Integer(required=True, default=1)
    week_count = fields.Integer(
        required=True,
        default=4,
        help="Number of consecutive weeks to generate.",
    )
    overwrite = fields.Boolean(
        help="Overwrite shifts already assigned to the rotation "
        "employees. When unchecked, existing assignments are kept.",
    )

    def action_apply(self):
        self.ensure_one()
        rotation = self.rotation_id
        weeks = rotation.week_ids.sorted("sequence")
        if not weeks:
            raise UserError(self.env._("The rotation has no week pattern defined."))
        if not rotation.assignment_ids:
            raise UserError(self.env._("The rotation has no employee assigned."))
        if self.week_from < 1 or self.week_from + self.week_count - 1 > 52:
            raise UserError(
                self.env._(
                    "The requested weeks must stay within the same year (1 to 52)."
                )
            )
        Planning = self.env["hr.shift.planning"]
        planning_ids = []
        for index in range(self.week_count):
            week_number = self.week_from + index
            planning = Planning.search(
                [("year", "=", self.year), ("week_number", "=", week_number)],
                limit=1,
            )
            if not planning:
                planning = Planning.create(
                    {"year": self.year, "week_number": week_number}
                )
            planning.generate_shifts()
            planning_ids.append(planning.id)
            for assignment in rotation.assignment_ids:
                pattern = weeks[(index + assignment.offset) % len(weeks)]
                lines = planning.shift_ids.line_ids.filtered(
                    lambda line, employee=assignment.employee_id: (
                        line.employee_id == employee
                    )
                )
                for pattern_line in pattern.line_ids:
                    day_lines = lines.filtered(
                        lambda line, day=pattern_line.day_number: (
                            line.day_number == day
                        )
                    )
                    # An employee can hold several lines the same day:
                    # fill a free one first, otherwise overwrite the first
                    line = (
                        day_lines.filtered(lambda line: not line.template_id)[:1]
                        or day_lines[:1]
                    )
                    if line and (not line.template_id or self.overwrite):
                        line.template_id = pattern_line.template_id
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.shift.planning",
            "view_mode": "list,form",
            "domain": [("id", "in", planning_ids)],
        }
