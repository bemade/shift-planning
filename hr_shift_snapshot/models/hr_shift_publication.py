# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
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
        """{(employee, day_number): template} of the planning right now."""
        self.ensure_one()
        return {
            (line.employee_id, line.day_number): line.template_id
            for line in self.planning_id.shift_ids.line_ids
            if line.template_id
        }

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
                    ("state", "=", "done"),
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
            published = {
                (line.employee_id, line.day_number): line
                for line in publication.line_ids
            }
            current = publication._current_assignments()
            values = []
            for key in published.keys() | current.keys():
                employee, day_number = key
                snapshot_line = published.get(key)
                published_template = snapshot_line and snapshot_line.template_id
                current_template = current.get(key)
                if (published_template or False) == (current_template or False):
                    continue
                cause, note = publication._detect_cause(employee, day_number)
                values.append(
                    {
                        "publication_id": publication.id,
                        "employee_id": employee.id,
                        "day_number": day_number,
                        "published_template_id": published_template
                        and published_template.id,
                        "published_template_name": snapshot_line
                        and snapshot_line.template_name,
                        "current_template_id": current_template and current_template.id,
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
