# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase

from odoo.addons.hr_shift_cascade_sms.models.hr_shift_sms_gateway import (
    HrShiftSmsGateway,
)


class TestShiftCascadeSms(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(cls.env.context, tracking_disable=True, tz="UTC")
        )
        cls.env.user.tz = "UTC"
        # 24/7 context: shifts are generated over the full week
        cls.env.company.shift_end_day = "6"
        cls.job_attendant = cls.env["hr.job"].create({"name": "Attendant"})
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Standard 40h", "tz": "UTC"}
        )
        cls.attendants = cls.env["hr.employee"].create(
            [
                {
                    "name": f"Attendant {number}",
                    "job_id": cls.job_attendant.id,
                    "resource_calendar_id": cls.calendar.id,
                    "shift_planning": True,
                    "mobile_phone": f"+1514555000{number}",
                }
                for number in range(3)
            ]
        )
        cls.template_night = cls.env["hr.shift.template"].create(
            {
                "name": "Night",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 23.0,
                "end_time": 7.0,
                "tz": "UTC",
            }
        )
        cls.rule = cls.env["hr.shift.coverage.rule"].create(
            {
                "template_id": cls.template_night.id,
                "job_id": cls.job_attendant.id,
                "min_employees": 1,
            }
        )
        cls.planning = cls.env["hr.shift.planning"].create(
            {"year": 2030, "week_number": 10}
        )
        cls.planning.generate_shifts()

    def _launch(self, day_number="0", blast=2):
        self.planning._update_coverage_gaps()
        gap = self.planning.coverage_gap_ids.filtered(
            lambda g: g.day_number == day_number
        )
        action = gap.action_launch_cascade()
        cascade = self.env["hr.shift.cascade"].browse(action["res_id"])
        cascade.write({"sms_enabled": True, "sms_blast_size": blast})
        return cascade

    def test_01_blast_dispatch(self):
        """Starting the cascade sends SMS to the first N candidates."""
        sent = []

        def fake_send(gateway, number, message):
            sent.append((number, message))
            return True

        with patch.object(HrShiftSmsGateway, "send", fake_send):
            cascade = self._launch(blast=2)
            cascade.action_start()
        candidates = cascade.candidate_ids
        self.assertEqual(len(sent), 2)
        self.assertTrue(candidates[0].sms_sent_on)
        self.assertTrue(candidates[1].sms_sent_on)
        self.assertFalse(candidates[2].sms_sent_on)
        self.assertIn(candidates[0].access_token, sent[0][1])

    def test_02_token_accept_and_race(self):
        """First token acceptance wins; the loser gets 'filled'."""
        with patch.object(HrShiftSmsGateway, "send", lambda *a: True):
            cascade = self._launch(blast=2)
            cascade.action_start()
        Candidate = self.env["hr.shift.cascade.candidate"]
        first, second = cascade.candidate_ids[0], cascade.candidate_ids[1]
        result = Candidate._token_action(first.access_token, "accept")
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(cascade.state, "filled")
        line = self.planning.shift_ids.line_ids.filtered(
            lambda line: line.employee_id == first.employee_id
            and line.day_number == "0"
        )
        self.assertEqual(line.template_id, self.template_night)
        # The second candidate answers too late
        late = Candidate._token_action(second.access_token, "accept")
        self.assertEqual(late["status"], "closed")

    def test_03_expiry_advances_cascade(self):
        """Expired offers become no_answer and the next candidate is hit."""
        with patch.object(HrShiftSmsGateway, "send", lambda *a: True):
            cascade = self._launch(blast=1)
            cascade.action_start()
            first = cascade.candidate_ids[0]
            self.assertTrue(first.sms_sent_on)
            # Simulate the timeout
            first.sudo().write(
                {
                    "sms_sent_on": fields.Datetime.now()
                    - timedelta(minutes=cascade.sms_timeout_minutes + 1)
                }
            )
            self.env["hr.shift.cascade"]._cron_process_sms()
        self.assertEqual(first.state, "no_answer")
        self.assertTrue(cascade.candidate_ids[1].sms_sent_on)

    def test_04_no_phone_skips_candidate(self):
        """A candidate without a phone number is skipped, not blocking."""
        self.attendants[0].write({"mobile_phone": False, "work_phone": False})
        with patch.object(HrShiftSmsGateway, "send", lambda *a: True):
            cascade = self._launch(blast=1)
            cascade.action_start()
        skipped = cascade.candidate_ids.filtered(
            lambda c: c.employee_id == self.attendants[0]
        )
        self.assertEqual(skipped.state, "skipped")
        self.assertEqual(len(cascade.candidate_ids.filtered("sms_sent_on")), 1)

    def test_05_gateway_failure_does_not_break(self):
        """A delivery failure is logged and the cascade keeps going."""
        with patch.object(HrShiftSmsGateway, "send", lambda *a: False):
            cascade = self._launch(blast=1)
            cascade.action_start()
        self.assertFalse(cascade.candidate_ids.filtered("sms_sent_on"))
        self.assertTrue(cascade.candidate_ids[0].note)
        self.assertEqual(cascade.state, "running")

    def test_06_invalid_token(self):
        result = self.env["hr.shift.cascade.candidate"]._token_action(
            "not-a-real-token", "accept"
        )
        self.assertEqual(result["status"], "invalid")
