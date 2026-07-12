# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from datetime import timedelta

from freezegun import freeze_time

from odoo.tests import TransactionCase


class TestSwapUrgentAutoApproval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(cls.env.context, tracking_disable=True, tz="UTC")
        )
        cls.env.user.tz = "UTC"
        cls.env.company.shift_end_day = "6"
        cls.env.company.swap_auto_approve_hours = 12
        cls.job = cls.env["hr.job"].create({"name": "Attendant"})
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Standard 40h", "tz": "UTC"}
        )
        cls.users = cls.env["res.users"].create(
            [
                {
                    "name": f"Swap User {number}",
                    "login": f"swap_urgent_{number}@test.example.com",
                    "email": f"swap_urgent_{number}@test.example.com",
                    "group_ids": [(4, cls.env.ref("base.group_user").id)],
                }
                for number in range(2)
            ]
        )
        cls.employees = cls.env["hr.employee"].create(
            [
                {
                    "name": f"Employee {number}",
                    "job_id": cls.job.id,
                    "resource_calendar_id": cls.calendar.id,
                    "shift_planning": True,
                    "user_id": user.id,
                }
                for number, user in enumerate(cls.users)
            ]
        )
        cls.template_evening = cls.env["hr.shift.template"].create(
            {
                "name": "Evening",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 16.0,
                "end_time": 0.25,
                "tz": "UTC",
            }
        )
        cls.planning = cls.env["hr.shift.planning"].create(
            {"year": 2030, "week_number": 10}
        )
        cls.planning.generate_shifts()
        cls.line = cls._line(cls.employees[0], "0")
        cls.line.template_id = cls.template_evening
        # Monday of that planning at 08:00 UTC: the 16:00 shift starts in 8h
        cls.monday_morning = f"{cls.planning.start_date} 08:00:00"

    @classmethod
    def _line(cls, employee, day_number):
        return cls.planning.shift_ids.line_ids.filtered(
            lambda line: line.employee_id == employee and line.day_number == day_number
        )

    def _make_swap(self):
        return (
            self.env["hr.shift.swap"]
            .with_user(self.users[0])
            .create(
                {
                    "line_id": self.line.id,
                    "employee_id": self.employees[0].id,
                    "target_employee_id": self.employees[1].id,
                    "planning_id": self.planning.id,
                }
            )
        )

    def test_01_urgent_swap_applies_on_acceptance(self):
        """Within the window, the colleague's acceptance applies the swap."""
        with freeze_time(self.monday_morning):
            swap = self._make_swap()
            swap.with_user(self.users[1]).action_accept()
        self.assertEqual(swap.state, "approved")
        self.assertFalse(self.line.template_id)
        target_line = self._line(self.employees[1], "0")
        self.assertEqual(target_line.template_id, self.template_evening)
        bodies = " ".join(swap.message_ids.mapped("body"))
        self.assertIn("Approved automatically", bodies)

    def test_02_distant_swap_still_needs_manager(self):
        """Outside the window, the flow is unchanged."""
        distant = f"{self.planning.start_date - timedelta(days=3)} 08:00:00"
        with freeze_time(distant):
            swap = self._make_swap()
            swap.with_user(self.users[1]).action_accept()
        self.assertEqual(swap.state, "accepted")
        self.assertEqual(self.line.template_id, self.template_evening)

    def test_03_disabled_window_never_auto_approves(self):
        self.env.company.swap_auto_approve_hours = 0
        with freeze_time(self.monday_morning):
            swap = self._make_swap()
            swap.with_user(self.users[1]).action_accept()
        self.assertEqual(swap.state, "accepted")
        self.assertEqual(self.line.template_id, self.template_evening)
