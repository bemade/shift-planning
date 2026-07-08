# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class HrShiftSwap(models.Model):
    _name = "hr.shift.swap"
    _description = "Shift Swap Request"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    line_id = fields.Many2one(
        comodel_name="hr.shift.planning.line",
        string="Offered Shift",
        required=True,
        ondelete="cascade",
        domain="[('employee_id', '=', employee_id), ('state', '=', 'assigned')]",
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
        default=lambda self: self.env.user.employee_id,
    )
    target_employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Colleague",
        required=True,
    )
    target_line_id = fields.Many2one(
        comodel_name="hr.shift.planning.line",
        string="Shift Requested in Exchange",
        ondelete="cascade",
        domain="[('employee_id', '=', target_employee_id), ('state', '=', 'assigned')]",
        help="Leave empty to simply hand the shift over to the colleague.",
    )
    planning_id = fields.Many2one(
        related="line_id.planning_id",
        store=True,
    )
    state = fields.Selection(
        selection=[
            ("submitted", "Waiting for Colleague"),
            ("accepted", "Waiting for Manager"),
            ("approved", "Approved"),
            ("refused", "Refused"),
            ("cancelled", "Cancelled"),
        ],
        default="submitted",
        tracking=True,
    )

    @api.depends("employee_id", "target_employee_id", "line_id")
    def _compute_display_name(self):
        for swap in self:
            swap.display_name = (
                f"{swap.employee_id.display_name} → "
                f"{swap.target_employee_id.display_name}: "
                f"{swap.line_id.display_name}"
            )

    @api.model_create_multi
    def create(self, vals_list):
        swaps = super().create(vals_list)
        for swap in swaps:
            partners = (
                swap.employee_id.user_id.partner_id
                | swap.target_employee_id.user_id.partner_id
            )
            swap.message_subscribe(partner_ids=partners.ids)
            swap.message_post(
                body=self.env._(
                    "%(employee)s proposes a shift swap to %(target)s.",
                    employee=swap.employee_id.display_name,
                    target=swap.target_employee_id.display_name,
                ),
                partner_ids=swap.target_employee_id.user_id.partner_id.ids,
            )
        return swaps

    def action_accept(self):
        for swap in self:
            if swap.state != "submitted":
                raise UserError(self.env._("Only submitted swaps can be accepted."))
            is_target = (
                swap.target_employee_id.user_id
                and swap.target_employee_id.user_id == self.env.user
            )
            if not is_target and not self.env.user.has_group(
                "hr_shift.group_shift_manager"
            ):
                raise AccessError(
                    self.env._("Only the requested colleague can accept a swap.")
                )
        self.write({"state": "accepted"})

    def action_approve(self):
        if not self.env.user.has_group("hr_shift.group_shift_manager"):
            raise AccessError(self.env._("Only shift managers can approve swaps."))
        for swap in self:
            if swap.state != "accepted":
                raise UserError(
                    self.env._(
                        "The colleague must accept the swap before the "
                        "manager approves it."
                    )
                )
            swap._apply()
            swap.state = "approved"
            swap.planning_id._update_coverage_gaps()

    def _apply(self):
        self.ensure_one()
        template = self.line_id.template_id
        if self.target_line_id:
            self.line_id.template_id = self.target_line_id.template_id
            self.target_line_id.template_id = template
            return
        target_line = self.env["hr.shift.planning.line"].search(
            [
                ("planning_id", "=", self.line_id.planning_id.id),
                ("employee_id", "=", self.target_employee_id.id),
                ("day_number", "=", self.line_id.day_number),
            ],
            limit=1,
        )
        if not target_line:
            raise UserError(
                self.env._(
                    "%(employee)s has no generated shift on that day in this planning.",
                    employee=self.target_employee_id.display_name,
                )
            )
        if target_line.template_id:
            raise UserError(
                self.env._(
                    "%(employee)s is already assigned on that day.",
                    employee=self.target_employee_id.display_name,
                )
            )
        target_line.template_id = template
        self.line_id.template_id = False

    def action_refuse(self):
        for swap in self:
            is_target = (
                swap.target_employee_id.user_id
                and swap.target_employee_id.user_id == self.env.user
            )
            if not is_target and not self.env.user.has_group(
                "hr_shift.group_shift_manager"
            ):
                raise AccessError(
                    self.env._(
                        "Only the requested colleague or a shift manager can "
                        "refuse a swap."
                    )
                )
        self.write({"state": "refused"})

    def action_cancel(self):
        for swap in self:
            if swap.state not in ("submitted", "accepted"):
                raise UserError(self.env._("Only pending swaps can be cancelled."))
        self.write({"state": "cancelled"})
