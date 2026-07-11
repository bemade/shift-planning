# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models

from odoo.addons.hr_shift.models.shift_template import WEEK_DAYS_SELECTION


class ShiftPlanning(models.Model):
    _name = "hr.shift.planning"
    _inherit = ["hr.shift.planning", "mail.thread"]

    publication_ids = fields.One2many(
        comodel_name="hr.shift.publication",
        inverse_name="planning_id",
    )
    publication_count = fields.Integer(compute="_compute_publication_count")

    @api.depends("publication_ids")
    def _compute_publication_count(self):
        for planning in self:
            planning.publication_count = len(planning.publication_ids)

    def action_publish(self):
        result = super().action_publish()
        self._create_publication_snapshot()
        return result

    def _create_publication_snapshot(self):
        self.ensure_one()
        self.env["hr.shift.publication"].create(
            {
                "planning_id": self.id,
                "version": len(self.publication_ids) + 1,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "employee_id": line.employee_id.id,
                            "employee_name": line.employee_id.display_name,
                            "day_number": line.day_number,
                            "template_id": line.template_id.id,
                            "template_name": line.template_id.display_name,
                        },
                    )
                    for line in self.shift_ids.line_ids
                    if line.template_id
                ],
            }
        )

    def action_view_publications(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "hr_shift_snapshot.hr_shift_publication_action"
        )
        action["domain"] = [("planning_id", "=", self.id)]
        action["context"] = {"default_planning_id": self.id}
        return action


class ShiftPlanningLine(models.Model):
    _inherit = "hr.shift.planning.line"

    def write(self, vals):
        if "template_id" not in vals:
            return super().write(vals)
        tracked = [
            (line, line.template_id) for line in self if line.planning_id.published_on
        ]
        result = super().write(vals)
        day_labels = dict(WEEK_DAYS_SELECTION)
        for line, previous_template in tracked:
            if line.template_id == previous_template:
                continue
            line.planning_id.message_post(
                body=self.env._(
                    "Change after publication — %(employee)s, %(day)s: "
                    "%(before)s → %(after)s",
                    employee=line.employee_id.display_name,
                    day=day_labels.get(line.day_number, line.day_number),
                    before=previous_template.display_name or self.env._("Unassigned"),
                    after=line.template_id.display_name or self.env._("Unassigned"),
                )
            )
        return result
