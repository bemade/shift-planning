# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.hr_shift.models.shift_template import WEEK_DAYS_SELECTION


class HrShiftCascade(models.Model):
    _name = "hr.shift.cascade"
    _description = "Shift Replacement Cascade"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    planning_id = fields.Many2one(
        comodel_name="hr.shift.planning",
        required=True,
        ondelete="cascade",
    )
    template_id = fields.Many2one(
        comodel_name="hr.shift.template",
        required=True,
        ondelete="cascade",
    )
    day_number = fields.Selection(
        selection=WEEK_DAYS_SELECTION,
        required=True,
    )
    rule_id = fields.Many2one(
        comodel_name="hr.shift.coverage.rule",
        help="Coverage rule this cascade fills. Its job position and "
        "department restrict the candidate list.",
    )
    candidate_ids = fields.One2many(
        comodel_name="hr.shift.cascade.candidate",
        inverse_name="cascade_id",
    )
    claim_id = fields.Many2one(
        comodel_name="hr.shift.claim",
        readonly=True,
        help="Claim created and approved when a candidate accepts.",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("running", "Running"),
            ("filled", "Filled"),
            ("exhausted", "Exhausted"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )

    @api.depends("template_id", "day_number", "planning_id")
    def _compute_display_name(self):
        for cascade in self:
            day = dict(WEEK_DAYS_SELECTION).get(cascade.day_number, "")
            cascade.display_name = (
                f"{cascade.template_id.display_name} / {day} — "
                f"{cascade.planning_id.display_name}"
            )

    def _get_candidate_lines(self):
        """Free shift lines of potential candidates for this slot."""
        self.ensure_one()
        lines = self.planning_id.shift_ids.line_ids.filtered(
            lambda line: line.day_number == self.day_number
            and line.state == "unassigned"
            and not line.template_id
        )
        if self.rule_id.job_id:
            lines = lines.filtered(
                lambda line: line.employee_id.job_id == self.rule_id.job_id
            )
        if self.rule_id.department_id:
            lines = lines.filtered(
                lambda line: line.employee_id.department_id
                == self.rule_id.department_id
            )
        return lines

    def _get_busy_candidate_employees(self):
        """Employees already working that day who could still take this
        slot as an extra shift: right job and department, no free line
        left on the day, not on leave, and none of their assigned shifts
        overlapping the offered one."""
        self.ensure_one()
        employees = self.env["hr.employee"]
        for shift in self.planning_id.shift_ids:
            employee = shift.employee_id
            if self.rule_id.job_id and employee.job_id != self.rule_id.job_id:
                continue
            if (
                self.rule_id.department_id
                and employee.department_id != self.rule_id.department_id
            ):
                continue
            day_lines = shift.line_ids.filtered(
                lambda line: line.day_number == self.day_number
            )
            assigned = day_lines.filtered(lambda line: line.state == "assigned")
            if not assigned or len(assigned) != len(day_lines):
                # No shift that day, a free line (regular candidate
                # already), or an on-leave/holiday line.
                continue
            if any(line.template_id._overlaps(self.template_id) for line in assigned):
                continue
            employees |= employee
        return employees

    def _employee_matches_availability(self, employee):
        """Employees without any declaration are considered available;
        employees who declared availabilities must have a matching one."""
        self.ensure_one()
        availabilities = self.env["hr.shift.availability"].search(
            [("employee_id", "=", employee.id)]
        )
        if not availabilities:
            return True
        return availabilities._matches(self.template_id, self.day_number)

    def _get_last_offered(self, employee):
        last_candidate = self.env["hr.shift.cascade.candidate"].search(
            [
                ("employee_id", "=", employee.id),
                ("contacted_on", "!=", False),
            ],
            order="contacted_on desc",
            limit=1,
        )
        return last_candidate.contacted_on or False

    def _prepare_candidate_entry(self, employee, line):
        self.ensure_one()
        assigned_lines = self.planning_id.shift_ids.line_ids.filtered(
            lambda planning_line, employee=employee: (
                planning_line.employee_id == employee
                and planning_line.state == "assigned"
            )
        )
        return {
            "employee": employee,
            "line": line,
            "hours": sum(
                # hr_shift computes a negative duration for
                # shifts crossing midnight (start and end are
                # combined on the same date): normalize to the
                # real elapsed time.
                duration if duration >= 0 else duration + 24
                for duration in assigned_lines.mapped("duration_hours")
            ),
            "last_offered": self._get_last_offered(employee),
        }

    def action_generate_candidates(self):
        """(Re)build the ordered candidate list.

        Two tiers: employees with a free line on the day first, then
        employees already working that day whose shifts leave room for
        this one (they get an extra line if they accept). Within each
        tier: fewest assigned hours in the week first (overtime
        control), then least recently offered (fairness rotation), then
        name for determinism. The coordinator can reorder manually
        afterwards — that manual override is the human recourse required
        for automated decisions.
        """

        def sort_key(entry):
            return (
                entry["hours"],
                entry["last_offered"]
                or fields.Datetime.from_string("1970-01-01 00:00:00"),
                entry["employee"].name or "",
            )

        for cascade in self:
            if cascade.state not in ("draft", "running"):
                raise UserError(
                    self.env._(
                        "Candidates can only be regenerated on a draft or "
                        "running cascade."
                    )
                )
            cascade.candidate_ids.unlink()
            free_entries = []
            seen = self.env["hr.employee"]
            for line in cascade._get_candidate_lines():
                employee = line.employee_id
                # One candidacy per employee, even with several free lines
                if employee in seen or not cascade._employee_matches_availability(
                    employee
                ):
                    continue
                seen |= employee
                free_entries.append(cascade._prepare_candidate_entry(employee, line))
            busy_entries = [
                cascade._prepare_candidate_entry(employee, None)
                for employee in cascade._get_busy_candidate_employees()
                if cascade._employee_matches_availability(employee)
            ]
            free_entries.sort(key=sort_key)
            busy_entries.sort(key=sort_key)
            self.env["hr.shift.cascade.candidate"].create(
                [
                    {
                        "cascade_id": cascade.id,
                        "sequence": index + 1,
                        "employee_id": entry["employee"].id,
                        "line_id": entry["line"] and entry["line"].id,
                        "is_extra_line": not entry["line"],
                        "week_hours": entry["hours"],
                        "last_offered": entry["last_offered"],
                    }
                    for index, entry in enumerate(free_entries + busy_entries)
                ]
            )

    def action_start(self):
        for cascade in self:
            if cascade.state != "draft":
                raise UserError(self.env._("Only draft cascades can be started."))
            if not cascade.candidate_ids:
                cascade.action_generate_candidates()
            if not cascade.candidate_ids:
                raise UserError(
                    self.env._(
                        "No eligible candidate for this slot: no employee "
                        "matches the job, department and availability "
                        "criteria with room left on that day."
                    )
                )
        self.write({"state": "running"})

    def action_cancel(self):
        for cascade in self:
            if cascade.state not in ("draft", "running"):
                raise UserError(self.env._("Only pending cascades can be cancelled."))
        self.write({"state": "cancelled"})

    def _check_exhausted(self):
        for cascade in self:
            if cascade.state == "running" and all(
                candidate.state in ("declined", "no_answer", "skipped")
                for candidate in cascade.candidate_ids
            ):
                cascade.state = "exhausted"
                cascade.message_post(
                    body=self.env._(
                        "Every candidate was contacted without success: "
                        "the slot is still open. Manual intervention "
                        "required."
                    )
                )

    def _fill(self, candidate):
        self.ensure_one()
        if candidate.is_extra_line and not candidate.line_id:
            # The employee already works that day: give them an extra
            # line, which the approved claim below will assign.
            shift = self.planning_id.shift_ids.filtered(
                lambda shift: shift.employee_id == candidate.employee_id
            )
            candidate.line_id = shift.action_add_line(self.day_number)
        claim = self.env["hr.shift.claim"].create(
            {
                "planning_id": self.planning_id.id,
                "template_id": self.template_id.id,
                "day_number": self.day_number,
                "employee_id": candidate.employee_id.id,
            }
        )
        claim.action_approve()
        self.write({"state": "filled", "claim_id": claim.id})
        remaining = self.candidate_ids.filtered(
            lambda other: other.state == "pending" and other != candidate
        )
        remaining.write({"state": "skipped"})
        self.message_post(
            body=self.env._(
                "Shift filled by %(employee)s.",
                employee=candidate.employee_id.display_name,
            )
        )


class HrShiftCascadeCandidate(models.Model):
    _name = "hr.shift.cascade.candidate"
    _description = "Shift Replacement Cascade Candidate"
    _order = "sequence, id"

    cascade_id = fields.Many2one(
        comodel_name="hr.shift.cascade",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
        ondelete="cascade",
    )
    line_id = fields.Many2one(
        comodel_name="hr.shift.planning.line",
        ondelete="cascade",
        help="Free line the acceptance will assign. Empty for an "
        "employee already working that day: the extra line is created "
        "when they accept.",
    )
    is_extra_line = fields.Boolean(
        string="Extra Shift",
        readonly=True,
        help="The employee already works that day: accepting adds this "
        "shift on top of their existing ones.",
    )
    week_hours = fields.Float(
        string="Assigned Hours (week)",
        readonly=True,
        help="Hours already assigned to this employee in the planning "
        "week when the list was generated.",
    )
    last_offered = fields.Datetime(
        readonly=True,
        help="Last time this employee was offered a replacement, for "
        "fairness rotation.",
    )
    work_phone = fields.Char(related="employee_id.work_phone")
    contacted_on = fields.Datetime(readonly=True)
    note = fields.Char()
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("declined", "Declined"),
            ("no_answer", "No Answer"),
            ("skipped", "Skipped"),
        ],
        default="pending",
    )

    def _check_actionable(self):
        for candidate in self:
            if candidate.cascade_id.state != "running":
                raise UserError(
                    self.env._("Start the cascade before logging outcomes.")
                )
            if candidate.state != "pending":
                raise UserError(self.env._("This candidate was already contacted."))

    def action_accept(self):
        self.ensure_one()
        self._check_actionable()
        self.write({"state": "accepted", "contacted_on": fields.Datetime.now()})
        self.cascade_id._fill(self)

    def action_decline(self):
        self._check_actionable()
        self.write({"state": "declined", "contacted_on": fields.Datetime.now()})
        self.cascade_id._check_exhausted()

    def action_no_answer(self):
        self._check_actionable()
        self.write({"state": "no_answer", "contacted_on": fields.Datetime.now()})
        self.cascade_id._check_exhausted()
