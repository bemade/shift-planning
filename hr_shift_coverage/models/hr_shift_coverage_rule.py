# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models

from odoo.addons.hr_shift.models.shift_template import WEEK_DAYS_SELECTION


class HrShiftCoverageRule(models.Model):
    _name = "hr.shift.coverage.rule"
    _description = "Shift Coverage Rule"

    template_id = fields.Many2one(
        comodel_name="hr.shift.template",
        required=True,
        ondelete="cascade",
    )
    job_id = fields.Many2one(
        comodel_name="hr.job",
        string="Job Position",
        help="If set, only employees holding this job position count towards "
        "the required staffing. Leave empty to count any assigned employee.",
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        help="If set, only employees of this department count towards the "
        "required staffing.",
    )
    min_employees = fields.Integer(
        string="Minimum Employees",
        required=True,
        default=1,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    _min_employees_positive = models.Constraint(
        "CHECK(min_employees > 0)",
        "The minimum number of employees must be strictly positive.",
    )

    @api.depends("template_id", "job_id", "min_employees")
    def _compute_display_name(self):
        for rule in self:
            parts = [rule.template_id.display_name or ""]
            if rule.job_id:
                parts.append(rule.job_id.display_name)
            parts.append(f"≥ {rule.min_employees}")
            rule.display_name = " — ".join(p for p in parts if p)

    def _filter_rule_lines(self, lines, template, day_number):
        """Lines matching this rule's job/department filters for a given
        template and day."""
        self.ensure_one()
        lines = lines.filtered(
            lambda line: line.template_id == template and line.day_number == day_number
        )
        if self.job_id:
            lines = lines.filtered(lambda line: line.employee_id.job_id == self.job_id)
        if self.department_id:
            lines = lines.filtered(
                lambda line: line.employee_id.department_id == self.department_id
            )
        return lines

    def _covering_line_count(self, lines, day_number):
        """How many employees the given assigned lines contribute towards
        this rule on that day. Extension point for alternate coverage
        sources (e.g. split shifts)."""
        self.ensure_one()
        return len(self._filter_rule_lines(lines, self.template_id, day_number))

    def _get_covered_day_numbers(self):
        """Day numbers ("0".."6") on which this rule requires staffing,
        derived from the template week days span (wrapping over the week
        boundary when start > end). Defaults to the full week when the
        template doesn't define a span."""
        self.ensure_one()
        all_days = [d[0] for d in WEEK_DAYS_SELECTION]
        start = self.template_id.day_of_week_start
        end = self.template_id.day_of_week_end
        if not start or not end:
            return all_days
        start_i, end_i = int(start), int(end)
        if start_i <= end_i:
            return [str(d) for d in range(start_i, end_i + 1)]
        return [str(d) for d in range(start_i, 7)] + [
            str(d) for d in range(0, end_i + 1)
        ]
