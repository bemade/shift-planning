# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models

from odoo.addons.hr_shift.models.shift_template import WEEK_DAYS_SELECTION


class HrShiftAvailability(models.Model):
    _name = "hr.shift.availability"
    _description = "Shift Availability"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
        default=lambda self: self.env.user.employee_id,
        ondelete="cascade",
    )
    template_id = fields.Many2one(
        comodel_name="hr.shift.template",
        help="Shift the employee is available for. Leave empty for any shift.",
    )
    day_number = fields.Selection(
        selection=WEEK_DAYS_SELECTION,
        help="Week day the employee is available on. Leave empty for any day.",
    )
    note = fields.Char()

    _employee_template_day_uniq = models.Constraint(
        "unique(employee_id, template_id, day_number)",
        "This availability is already declared.",
    )

    @api.depends("employee_id", "template_id", "day_number")
    def _compute_display_name(self):
        any_label = self.env._("Any")
        for availability in self:
            template = availability.template_id.display_name or any_label
            day = (
                dict(WEEK_DAYS_SELECTION).get(availability.day_number)
                if availability.day_number
                else any_label
            )
            availability.display_name = (
                f"{availability.employee_id.display_name}: {template} / {day}"
            )

    def _matches(self, template, day_number):
        """Whether one of these availabilities matches the given slot."""
        return any(
            (not availability.template_id or availability.template_id == template)
            and (not availability.day_number or availability.day_number == day_number)
            for availability in self
        )
