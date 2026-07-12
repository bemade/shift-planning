# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import uuid
from datetime import timedelta

from odoo import api, fields, models


class HrShiftCascade(models.Model):
    _inherit = "hr.shift.cascade"

    sms_enabled = fields.Boolean(
        string="Send SMS Offers",
        default=lambda self: self.env["ir.config_parameter"]
        .sudo()
        .get_param("hr_shift_cascade_sms.enabled_by_default", "False")
        == "True",
    )
    sms_blast_size = fields.Integer(
        string="Simultaneous SMS Offers",
        default=3,
        help="Number of candidates contacted at the same time. The first "
        "one to accept gets the shift.",
    )
    sms_timeout_minutes = fields.Integer(
        string="SMS Timeout (minutes)",
        default=15,
        help="Without an answer after this delay, the offer expires and "
        "the next candidate is contacted.",
    )

    def action_start(self):
        result = super().action_start()
        self.filtered("sms_enabled")._sms_dispatch()
        return result

    def _sms_dispatch(self):
        """Keep up to sms_blast_size pending offers in flight."""
        for cascade in self:
            if cascade.state != "running" or not cascade.sms_enabled:
                continue
            pending = cascade.candidate_ids.filtered(
                lambda candidate: candidate.state == "pending"
            )
            in_flight = pending.filtered("sms_sent_on")
            for candidate in pending - in_flight:
                if len(in_flight) >= max(cascade.sms_blast_size, 1):
                    break
                if candidate._sms_send():
                    in_flight |= candidate

    def _sms_expire(self):
        expiry_message = self.env._("SMS offer expired without an answer.")
        for cascade in self:
            if cascade.state != "running" or not cascade.sms_enabled:
                continue
            deadline = fields.Datetime.now() - timedelta(
                minutes=max(cascade.sms_timeout_minutes, 1)
            )
            expired = cascade.candidate_ids.filtered(
                lambda candidate, deadline=deadline: candidate.state == "pending"
                and candidate.sms_sent_on
                and candidate.sms_sent_on < deadline
            )
            for candidate in expired:
                candidate.write(
                    {
                        "state": "no_answer",
                        "contacted_on": fields.Datetime.now(),
                        "note": expiry_message,
                    }
                )
            cascade._check_exhausted()

    @api.model
    def _cron_process_sms(self):
        cascades = self.search([("state", "=", "running"), ("sms_enabled", "=", True)])
        cascades._sms_expire()
        cascades._sms_dispatch()


class HrShiftCascadeCandidate(models.Model):
    _inherit = "hr.shift.cascade.candidate"

    access_token = fields.Char(
        default=lambda self: uuid.uuid4().hex,
        copy=False,
        index=True,
    )
    mobile_phone = fields.Char(related="employee_id.mobile_phone")
    sms_sent_on = fields.Datetime(readonly=True)

    def _get_token_url(self):
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return f"{base_url}/shift_cascade/{self.access_token}"

    def _sms_body(self):
        self.ensure_one()
        return self.env._(
            "Replacement shift available: %(shift)s. Answer here: %(url)s",
            shift=self.cascade_id.display_name,
            url=self._get_token_url(),
        )

    def _sms_number(self):
        """Phone number normalized for HTTP gateways: digits only, with
        the leading ``+`` preserved when present."""
        self.ensure_one()
        raw = self.mobile_phone or self.work_phone or ""
        digits = "".join(char for char in raw if char.isdigit())
        if not digits:
            return ""
        return f"+{digits}" if raw.strip().startswith("+") else digits

    def _sms_send(self):
        """Send the offer to this candidate. Returns True on success."""
        self.ensure_one()
        number = self._sms_number()
        if not number:
            self.write(
                {
                    "state": "skipped",
                    "note": self.env._("No phone number on the employee."),
                }
            )
            return False
        if not self.env["hr.shift.sms.gateway"].send(number, self._sms_body()):
            self.note = self.env._("SMS delivery failed.")
            return False
        self.sms_sent_on = fields.Datetime.now()
        return True

    @api.model
    def _token_get(self, token):
        return self.sudo().search([("access_token", "=", token)], limit=1)

    @api.model
    def _token_action(self, token, action=None):
        """Resolve a tokenized answer. Returns the rendering status.

        Possible statuses: invalid, filled, closed, answered, pending,
        accepted, declined.
        """
        candidate = self._token_get(token)
        if not candidate:
            return {"status": "invalid"}
        cascade = candidate.cascade_id
        values = {
            "candidate": candidate,
            "shift_label": cascade.display_name,
        }
        if candidate.state != "pending":
            values["status"] = "answered" if candidate.state == "accepted" else "closed"
            return values
        if cascade.state == "filled":
            values["status"] = "filled"
            return values
        if cascade.state != "running":
            values["status"] = "closed"
            return values
        if action == "accept":
            candidate.action_accept()
            values["status"] = "accepted"
        elif action == "decline":
            candidate.action_decline()
            values["status"] = "declined"
        else:
            values["status"] = "pending"
        return values
