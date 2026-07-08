# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.tests import TransactionCase


class TestPublish(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(cls.env.context, tracking_disable=True, tz="UTC")
        )
        cls.env.user.tz = "UTC"
        cls.env.company.shift_end_day = "6"
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Standard", "tz": "UTC"}
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Employee",
                "resource_calendar_id": cls.calendar.id,
                "shift_planning": True,
                "work_email": "employee@test.example.com",
            }
        )
        cls.template = cls.env["hr.shift.template"].create(
            {
                "name": "Day",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 7.0,
                "end_time": 15.0,
                "tz": "UTC",
            }
        )
        cls.planning = cls.env["hr.shift.planning"].create(
            {"year": 2030, "week_number": 10}
        )
        cls.planning.generate_shifts()
        cls.shift = cls.planning.shift_ids
        cls.shift.line_ids.filtered(
            lambda line: line.day_number == "0"
        ).template_id = cls.template

    def test_01_publish_sends_mail(self):
        before = self.env["mail.mail"].sudo().search_count([])
        action = self.planning.action_publish()
        self.assertEqual(action["params"]["type"], "success")
        after = self.env["mail.mail"].sudo().search_count([])
        self.assertEqual(after - before, 1)
        self.assertTrue(self.planning.published_on)

    def test_02_token_page(self):
        values = self.env["hr.shift.planning.shift"]._schedule_page_values(
            self.shift.schedule_token
        )
        self.assertEqual(values["status"], "ok")
        self.assertEqual(values["employee_name"], "Employee")
        self.assertEqual(len(values["lines"]), 1)
        self.assertEqual(values["lines"][0]["template"], "Day")
        invalid = self.env["hr.shift.planning.shift"]._schedule_page_values("bad-token")
        self.assertEqual(invalid["status"], "invalid")
