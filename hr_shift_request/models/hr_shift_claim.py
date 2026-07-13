# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.hr_shift.models.shift_template import (
    WEEK_DAYS_SELECTION,
    translated_week_days,
)


class HrShiftClaim(models.Model):
    _name = "hr.shift.claim"
    _description = "Open Shift Claim"
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
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
        default=lambda self: self.env.user.employee_id,
    )
    line_id = fields.Many2one(
        comodel_name="hr.shift.planning.line",
        readonly=True,
        help="Shift line assigned when the claim is approved.",
    )
    state = fields.Selection(
        selection=[
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("refused", "Refused"),
            ("cancelled", "Cancelled"),
        ],
        default="submitted",
        tracking=True,
    )

    @api.depends("employee_id", "template_id", "day_number")
    def _compute_display_name(self):
        for claim in self:
            day = translated_week_days(claim.env).get(claim.day_number, "")
            claim.display_name = (
                f"{claim.employee_id.display_name}: "
                f"{claim.template_id.display_name} / {day}"
            )

    @api.model_create_multi
    def create(self, vals_list):
        claims = super().create(vals_list)
        managers = self.env.ref("hr_shift.group_shift_manager").user_ids
        for claim in claims:
            claim.message_subscribe(
                partner_ids=claim.employee_id.user_id.partner_id.ids
            )
            claim.message_post(
                body=self.env._(
                    "%(employee)s claims the shift %(shift)s.",
                    employee=claim.employee_id.display_name,
                    shift=claim.display_name,
                ),
                partner_ids=managers.partner_id.ids,
            )
        return claims

    def _check_manager(self):
        if self.env.su:
            # System flows (e.g. tokenized cascade acceptances) approve
            # through sudo: the capability was granted upstream.
            return
        if not self.env.user.has_group("hr_shift.group_shift_manager"):
            raise AccessError(
                self.env._("Only shift managers can approve or refuse claims.")
            )

    def _get_employee_line(self):
        """Line of the employee for the claimed day, preferring a free
        one: an employee can hold several lines the same day."""
        self.ensure_one()
        lines = self.env["hr.shift.planning.line"].search(
            [
                ("planning_id", "=", self.planning_id.id),
                ("employee_id", "=", self.employee_id.id),
                ("day_number", "=", self.day_number),
            ]
        )
        return lines.filtered(lambda line: line.state == "unassigned")[:1] or lines[:1]

    def action_approve(self):
        self._check_manager()
        for claim in self:
            if claim.state != "submitted":
                raise UserError(self.env._("Only submitted claims can be approved."))
            line = claim._get_employee_line()
            if not line:
                raise UserError(
                    self.env._(
                        "%(employee)s has no generated shift on that day in "
                        "this planning. Generate the planning shifts first.",
                        employee=claim.employee_id.display_name,
                    )
                )
            if line.template_id:
                raise UserError(
                    self.env._(
                        "%(employee)s is already assigned to %(template)s on that day.",
                        employee=claim.employee_id.display_name,
                        template=line.template_id.display_name,
                    )
                )
            line.template_id = claim.template_id
            claim.write({"state": "approved", "line_id": line.id})
            claim.planning_id._update_coverage_gaps()

    def action_refuse(self):
        self._check_manager()
        self.write({"state": "refused"})

    def action_cancel(self):
        for claim in self:
            if claim.state != "submitted":
                raise UserError(self.env._("Only submitted claims can be cancelled."))
        self.write({"state": "cancelled"})
