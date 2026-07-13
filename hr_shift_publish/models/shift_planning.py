# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import uuid
from datetime import timedelta

from odoo import api, fields, models


class ShiftPlanningShift(models.Model):
    _inherit = "hr.shift.planning.shift"

    schedule_token = fields.Char(
        default=lambda self: uuid.uuid4().hex,
        copy=False,
        index=True,
    )

    def _get_schedule_url(self):
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return f"{base_url}/shift_schedule/{self.schedule_token}"

    def _get_schedule_lines(self):
        """Assigned lines of the week, rendered day by day."""
        self.ensure_one()
        day_labels = dict(
            self.line_ids._fields["day_number"]._description_selection(self.env)
        )
        start = self.planning_id.start_date
        return [
            {
                "day": day_labels.get(line.day_number, ""),
                "date": start + timedelta(days=int(line.day_number))
                if start
                else False,
                "template": line.template_id.display_name,
            }
            for line in self.line_ids.filtered(
                lambda line: line.state == "assigned"
            ).sorted("day_number")
        ]

    @api.model
    def _schedule_page_values(self, token):
        shift = self.sudo().search([("schedule_token", "=", token)], limit=1)
        if not shift:
            return {"status": "invalid"}
        return {
            "status": "ok",
            "employee_name": shift.employee_id.name,
            "planning_label": shift.planning_id.display_name,
            "lines": shift._get_schedule_lines(),
        }


class ShiftPlanning(models.Model):
    _inherit = "hr.shift.planning"

    published_on = fields.Datetime(readonly=True, copy=False)

    def action_publish(self):
        """Email every employee of the planning their weekly schedule."""
        self.ensure_one()
        sent = 0
        for shift in self.shift_ids:
            email = shift.employee_id.work_email
            lines = shift._get_schedule_lines()
            if not email or not lines:
                continue
            rows = "".join(
                f"<li>{line['day']} ({line['date'] or ''}): {line['template']}</li>"
                for line in lines
            )
            body = self.env._(
                "%(name)s,<br/>Here is your schedule for %(week)s:"
                "<ul>%(rows)s</ul>"
                '<a href="%(url)s">See my schedule</a>',
                name=shift.employee_id.name,
                week=self.display_name,
                rows=rows,
                url=shift._get_schedule_url(),
            )
            self.env["mail.mail"].sudo().create(
                {
                    "email_to": email,
                    "subject": self.env._(
                        "Your schedule — %(week)s", week=self.display_name
                    ),
                    "body_html": f"<p>{body}</p>",
                }
            ).send()
            sent += 1
        self.published_on = fields.Datetime.now()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": self.env._("Schedule published"),
                "message": self.env._("%(sent)s employee(s) notified.", sent=sent),
                "sticky": False,
            },
        }
