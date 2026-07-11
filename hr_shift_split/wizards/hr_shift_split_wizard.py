# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models
from odoo.exceptions import UserError


class HrShiftSplitWizard(models.TransientModel):
    _name = "hr.shift.split.wizard"
    _description = "Split a shift into two replacement parts"

    line_id = fields.Many2one(
        comodel_name="hr.shift.planning.line",
        help="Assigned line to free and replace by two partial shifts.",
    )
    gap_id = fields.Many2one(
        comodel_name="hr.shift.coverage.gap",
        help="Open slot to fill with two partial shifts.",
    )
    template_id = fields.Many2one(
        comodel_name="hr.shift.template",
        compute="_compute_slot",
    )
    planning_id = fields.Many2one(
        comodel_name="hr.shift.planning",
        compute="_compute_slot",
    )
    day_number = fields.Char(compute="_compute_slot")
    cut_time = fields.Float(
        required=True,
        help="Clock time where the shift is cut in two.",
    )

    @api.depends("line_id", "gap_id")
    def _compute_slot(self):
        for wizard in self:
            source = wizard.line_id or wizard.gap_id
            wizard.template_id = source.template_id
            wizard.planning_id = source.planning_id
            wizard.day_number = source.day_number

    @api.onchange("line_id", "gap_id")
    def _onchange_slot(self):
        for wizard in self:
            template = wizard.template_id
            if template and not wizard.cut_time:
                midpoint = (
                    template.start_time
                    + (template._normalized_end() - template.start_time) / 2
                )
                wizard.cut_time = midpoint % 24

    def _find_rule(self):
        """Coverage rule restricting the candidates of the cascades."""
        self.ensure_one()
        if self.gap_id:
            return self.gap_id.rule_id
        employee = self.line_id.employee_id
        rules = self.env["hr.shift.coverage.rule"].search(
            [("template_id", "=", self.template_id.id)]
        )
        return next(
            iter(
                rules.filtered(
                    lambda rule: (
                        rule.job_id in (employee.job_id, self.env["hr.job"])
                        and rule.department_id
                        in (employee.department_id, self.env["hr.department"])
                    )
                )
            ),
            self.env["hr.shift.coverage.rule"],
        )

    def action_split(self):
        self.ensure_one()
        if not self.template_id:
            raise UserError(self.env._("Select an assigned line or an open slot."))
        first, second = self.template_id._get_or_create_split_pair(self.cut_time)
        rule = self._find_rule()
        planning = self.planning_id
        if self.line_id:
            employee = self.line_id.employee_id
            self.line_id.template_id = False
            if hasattr(planning, "message_post"):
                planning.message_post(
                    body=self.env._(
                        "Shift of %(employee)s split for replacement: "
                        "%(first)s + %(second)s",
                        employee=employee.display_name,
                        first=first.display_name,
                        second=second.display_name,
                    )
                )
        if "hr.shift.cascade" not in self.env:
            planning._update_coverage_gaps()
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "success",
                    "title": self.env._("Shift split"),
                    "message": self.env._(
                        "Partial shifts created: %(first)s and %(second)s. "
                        "Assign them from the planning.",
                        first=first.display_name,
                        second=second.display_name,
                    ),
                    "sticky": False,
                },
            }
        cascades = self.env["hr.shift.cascade"].create(
            [
                {
                    "planning_id": planning.id,
                    "template_id": part.id,
                    "day_number": self.day_number,
                    "rule_id": rule.id,
                }
                for part in (first, second)
            ]
        )
        cascades.action_generate_candidates()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Replacement cascades"),
            "res_model": "hr.shift.cascade",
            "view_mode": "list,form",
            "domain": [("id", "in", cascades.ids)],
        }
