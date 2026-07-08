# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from datetime import timedelta

from odoo import api, fields, models

from odoo.addons.hr_shift.models.shift_template import WEEK_DAYS_SELECTION


class HrShiftCoverageGap(models.Model):
    _name = "hr.shift.coverage.gap"
    _description = "Shift Coverage Gap"
    _order = "date, template_id"

    planning_id = fields.Many2one(
        comodel_name="hr.shift.planning",
        required=True,
        ondelete="cascade",
        index=True,
    )
    rule_id = fields.Many2one(
        comodel_name="hr.shift.coverage.rule",
        required=True,
        ondelete="cascade",
    )
    template_id = fields.Many2one(
        related="rule_id.template_id",
        store=True,
    )
    job_id = fields.Many2one(
        related="rule_id.job_id",
        store=True,
    )
    day_number = fields.Selection(
        selection=WEEK_DAYS_SELECTION,
        required=True,
    )
    date = fields.Date(compute="_compute_date", store=True)
    required = fields.Integer()
    assigned = fields.Integer()
    missing = fields.Integer()

    @api.depends("planning_id.start_date", "day_number")
    def _compute_date(self):
        for gap in self:
            start = gap.planning_id.start_date
            gap.date = start + timedelta(days=int(gap.day_number)) if start else False
