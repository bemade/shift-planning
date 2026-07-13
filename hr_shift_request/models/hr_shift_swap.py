# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from datetime import datetime, time, timedelta

import pytz

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
            # sudo: user_id is a private employee field the requesting
            # employee cannot read on the colleague's record.
            swap_su = swap.sudo()
            partners = (
                swap_su.employee_id.user_id.partner_id
                | swap_su.target_employee_id.user_id.partner_id
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
        for swap in self:
            swap._auto_approve_if_urgent()

    def _shift_start_datetime(self):
        """Naive UTC datetime at which the offered shift starts."""
        self.ensure_one()
        line = self.line_id
        start_date = line.planning_id.start_date
        if not start_date or not line.template_id:
            return False
        tz = pytz.timezone(line.template_id.tz or self.env.user.tz or "UTC")
        start_time = line.template_id.start_time
        local_start = tz.localize(
            datetime.combine(
                start_date + timedelta(days=int(line.day_number)),
                time(int(start_time) % 24, int(round(start_time % 1 * 60))),
            )
        )
        return local_start.astimezone(pytz.utc).replace(tzinfo=None)

    def _auto_approve_if_urgent(self):
        """Apply the swap without manager approval when the shift starts
        soon: an urgent slot must not stay empty for lack of a
        confirmation."""
        self.ensure_one()
        hours = self.env.company.swap_auto_approve_hours
        if not hours or self.state != "accepted":
            return
        start = self._shift_start_datetime()
        if not start or start - fields.Datetime.now() > timedelta(hours=hours):
            return
        swap = self.sudo()
        swap._apply()
        swap.state = "approved"
        swap.planning_id._update_coverage_gaps()
        self.message_post(
            body=self.env._(
                "Approved automatically: the shift starts in less than "
                "%(hours)s hours.",
                hours=round(hours),
            )
        )

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
        target_lines = self.env["hr.shift.planning.line"].search(
            [
                ("planning_id", "=", self.line_id.planning_id.id),
                ("employee_id", "=", self.target_employee_id.id),
                ("day_number", "=", self.line_id.day_number),
            ]
        )
        if not target_lines:
            raise UserError(
                self.env._(
                    "%(employee)s has no generated shift on that day in this planning.",
                    employee=self.target_employee_id.display_name,
                )
            )
        target_line = target_lines.filtered(lambda line: line.state == "unassigned")[:1]
        if not target_line:
            # The colleague already works that day: hand the shift over on
            # an extra line, unless the time windows overlap.
            assigned = target_lines.filtered(lambda line: line.state == "assigned")
            if not assigned:
                raise UserError(
                    self.env._(
                        "%(employee)s is not available on that day.",
                        employee=self.target_employee_id.display_name,
                    )
                )
            conflicting = assigned[0].shift_id._overlapping_lines(
                template, self.line_id.day_number
            )
            if conflicting:
                raise UserError(
                    self.env._(
                        "%(employee)s is already assigned to %(existing)s, "
                        "which overlaps %(new)s.",
                        employee=self.target_employee_id.display_name,
                        existing=conflicting[0].template_id.display_name,
                        new=template.display_name,
                    )
                )
            target_line = assigned[0].shift_id.action_add_line(self.line_id.day_number)
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
