# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from itertools import zip_longest

from odoo import api, fields, models

from odoo.addons.hr_shift.models.shift_template import WEEK_DAYS_SELECTION


class HrShiftPublication(models.Model):
    _name = "hr.shift.publication"
    _description = "Published Schedule Snapshot"
    _order = "published_on desc, id desc"

    planning_id = fields.Many2one(
        comodel_name="hr.shift.planning",
        required=True,
        ondelete="cascade",
        index=True,
    )
    version = fields.Integer(readonly=True, default=1)
    published_on = fields.Datetime(
        readonly=True, default=fields.Datetime.now, required=True
    )
    published_by_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        default=lambda self: self.env.user,
    )
    line_ids = fields.One2many(
        comodel_name="hr.shift.publication.line",
        inverse_name="publication_id",
        readonly=True,
    )
    variance_ids = fields.One2many(
        comodel_name="hr.shift.publication.variance",
        inverse_name="publication_id",
        readonly=True,
    )
    variance_count = fields.Integer(compute="_compute_variance_count")

    @api.depends("planning_id.display_name", "version")
    def _compute_display_name(self):
        for publication in self:
            publication.display_name = self.env._(
                "%(planning)s — v%(version)s",
                planning=publication.planning_id.display_name,
                version=publication.version,
            )

    @api.depends("variance_ids")
    def _compute_variance_count(self):
        for publication in self:
            publication.variance_count = len(publication.variance_ids)

    def _current_assignments(self):
        """{(employee, day_number): templates} of the planning right now.

        An employee can hold several shifts the same day, so the value
        is a recordset of every assigned template on the slot."""
        self.ensure_one()
        assignments = {}
        for line in self.planning_id.shift_ids.line_ids:
            if line.template_id:
                key = (line.employee_id, line.day_number)
                assignments[key] = (
                    assignments.get(key, self.env["hr.shift.template"])
                    | line.template_id
                )
        return assignments

    def _detect_cause(self, employee, day_number):
        """Best-effort explanation for a divergence on that slot."""
        # create_date (not published_on) so both sides come from the same
        # clock: write_date is the SQL transaction time, published_on the
        # Python wall clock.
        if "hr.shift.swap" in self.env:
            swap = self.env["hr.shift.swap"].search(
                [
                    ("planning_id", "=", self.planning_id.id),
                    ("state", "=", "approved"),
                    ("write_date", ">=", self.create_date),
                    "|",
                    ("employee_id", "=", employee.id),
                    ("target_employee_id", "=", employee.id),
                ],
                limit=1,
            )
            if swap and swap.line_id.day_number == day_number:
                return "swap", swap.display_name
        if "hr.shift.cascade" in self.env:
            cascade = self.env["hr.shift.cascade"].search(
                [
                    ("planning_id", "=", self.planning_id.id),
                    ("day_number", "=", day_number),
                    ("state", "=", "filled"),
                    ("claim_id.employee_id", "=", employee.id),
                    ("write_date", ">=", self.create_date),
                ],
                limit=1,
            )
            if cascade:
                return "cascade", cascade.display_name
        return "manual", False

    def action_compute_variances(self):
        """Rebuild the divergence list between this snapshot and the planning."""
        Variance = self.env["hr.shift.publication.variance"]
        for publication in self:
            publication.variance_ids.unlink()
            published = {}
            for line in publication.line_ids:
                published.setdefault((line.employee_id, line.day_number), []).append(
                    line
                )
            current = publication._current_assignments()
            values = []
            for key in published.keys() | current.keys():
                employee, day_number = key
                # Match published lines with the still-identical current
                # assignments; what remains on both sides diverged.
                remaining = list(current.get(key, []))
                changed_lines = []
                for snapshot_line in published.get(key, []):
                    if snapshot_line.template_id in remaining:
                        remaining.remove(snapshot_line.template_id)
                    else:
                        changed_lines.append(snapshot_line)
                if not changed_lines and not remaining:
                    continue
                cause, note = publication._detect_cause(employee, day_number)
                for snapshot_line, current_template in zip_longest(
                    changed_lines, remaining
                ):
                    values.append(
                        {
                            "publication_id": publication.id,
                            "employee_id": employee.id,
                            "day_number": day_number,
                            "published_template_id": snapshot_line
                            and snapshot_line.template_id.id,
                            "published_template_name": snapshot_line
                            and snapshot_line.template_name,
                            "current_template_id": current_template
                            and current_template.id,
                            "current_template_name": current_template
                            and current_template.display_name,
                            "cause": cause,
                            "cause_note": note,
                        }
                    )
            Variance.create(values)
        return True


class HrShiftPublicationLine(models.Model):
    _name = "hr.shift.publication.line"
    _description = "Published Schedule Snapshot Line"
    _order = "employee_id, day_number"

    publication_id = fields.Many2one(
        comodel_name="hr.shift.publication",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(comodel_name="hr.employee", ondelete="set null")
    employee_name = fields.Char(required=True)
    day_number = fields.Selection(selection=WEEK_DAYS_SELECTION, required=True)
    template_id = fields.Many2one(comodel_name="hr.shift.template", ondelete="set null")
    template_name = fields.Char(required=True)


class HrShiftPublicationVariance(models.Model):
    _name = "hr.shift.publication.variance"
    _description = "Variance Between Published and Current Schedule"
    _order = "employee_id, day_number"

    publication_id = fields.Many2one(
        comodel_name="hr.shift.publication",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(comodel_name="hr.employee", ondelete="set null")
    day_number = fields.Selection(selection=WEEK_DAYS_SELECTION)
    published_template_id = fields.Many2one(
        comodel_name="hr.shift.template", ondelete="set null"
    )
    published_template_name = fields.Char()
    current_template_id = fields.Many2one(
        comodel_name="hr.shift.template", ondelete="set null"
    )
    current_template_name = fields.Char()
    cause = fields.Selection(
        selection=[
            ("swap", "Shift swap"),
            ("cascade", "Replacement cascade"),
            ("manual", "Manual change"),
        ],
        readonly=True,
    )
    cause_note = fields.Char(readonly=True)
