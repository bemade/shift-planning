# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models

from odoo.addons.hr_shift.models.shift_template import WEEK_DAYS_SELECTION


class HrShiftRotation(models.Model):
    _name = "hr.shift.rotation"
    _description = "Shift Rotation Pattern"

    name = fields.Char(required=True)
    week_ids = fields.One2many(
        comodel_name="hr.shift.rotation.week",
        inverse_name="rotation_id",
    )
    assignment_ids = fields.One2many(
        comodel_name="hr.shift.rotation.assignment",
        inverse_name="rotation_id",
    )
    active = fields.Boolean(default=True)


class HrShiftRotationWeek(models.Model):
    _name = "hr.shift.rotation.week"
    _description = "Shift Rotation Week Pattern"
    _order = "sequence, id"

    rotation_id = fields.Many2one(
        comodel_name="hr.shift.rotation",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(help="E.g. 'Week on' / 'Week off' / 'Weekend only'.")
    line_ids = fields.One2many(
        comodel_name="hr.shift.rotation.week.line",
        inverse_name="week_id",
    )

    @api.depends("name", "sequence")
    def _compute_display_name(self):
        for week in self:
            week.display_name = week.name or self.env._(
                "Week %(number)s", number=week.sequence
            )


class HrShiftRotationWeekLine(models.Model):
    _name = "hr.shift.rotation.week.line"
    _description = "Shift Rotation Week Pattern Line"

    week_id = fields.Many2one(
        comodel_name="hr.shift.rotation.week",
        required=True,
        ondelete="cascade",
    )
    day_number = fields.Selection(
        selection=WEEK_DAYS_SELECTION,
        required=True,
    )
    template_id = fields.Many2one(
        comodel_name="hr.shift.template",
        required=True,
        ondelete="cascade",
    )

    _day_uniq = models.Constraint(
        "unique(week_id, day_number)",
        "A pattern week can only assign one shift per day.",
    )


class HrShiftRotationAssignment(models.Model):
    _name = "hr.shift.rotation.assignment"
    _description = "Shift Rotation Assignment"

    rotation_id = fields.Many2one(
        comodel_name="hr.shift.rotation",
        required=True,
        ondelete="cascade",
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
        ondelete="cascade",
    )
    offset = fields.Integer(
        help="Starting position in the rotation cycle. Two employees "
        "with offsets 0 and 1 on a two-week rotation alternate weeks.",
    )

    _employee_uniq = models.Constraint(
        "unique(rotation_id, employee_id)",
        "This employee is already assigned to this rotation.",
    )
