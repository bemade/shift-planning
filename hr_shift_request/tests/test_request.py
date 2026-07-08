# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase


class TestShiftRequest(TransactionCase):
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
        cls.users = cls.env["res.users"].create(
            [
                {
                    "name": f"Shift User {number}",
                    "login": f"shift_user_{number}@test.example.com",
                    "email": f"shift_user_{number}@test.example.com",
                    "group_ids": [(4, cls.env.ref("base.group_user").id)],
                }
                for number in range(2)
            ]
        )
        cls.employees = cls.env["hr.employee"].create(
            [
                {
                    "name": f"Employee {number}",
                    "job_id": cls.job_attendant.id,
                    "resource_calendar_id": cls.calendar.id,
                    "shift_planning": True,
                    "user_id": user.id,
                }
                for number, user in enumerate(cls.users)
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
        cls.template_day = cls.env["hr.shift.template"].create(
            {
                "name": "Day",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 7.0,
                "end_time": 15.0,
                "tz": "UTC",
            }
        )
        cls.rule = cls.env["hr.shift.coverage.rule"].create(
            {"template_id": cls.template_night.id, "min_employees": 1}
        )
        cls.planning = cls.env["hr.shift.planning"].create(
            {"year": 2030, "week_number": 10}
        )
        cls.planning.generate_shifts()

    def _line(self, employee, day_number):
        return self.planning.shift_ids.line_ids.filtered(
            lambda line: line.employee_id == employee and line.day_number == day_number
        )

    def test_01_claim_flow(self):
        """An approved claim assigns the line and closes the gap."""
        self.planning._update_coverage_gaps()
        gap = self.planning.coverage_gap_ids.filtered(lambda g: g.day_number == "0")
        action = gap.with_user(self.users[0]).action_claim()
        claim = self.env["hr.shift.claim"].browse(action["res_id"])
        self.assertEqual(claim.state, "submitted")
        self.assertEqual(claim.employee_id, self.employees[0])
        claim.action_approve()
        self.assertEqual(claim.state, "approved")
        line = self._line(self.employees[0], "0")
        self.assertEqual(line.template_id, self.template_night)
        self.assertEqual(claim.line_id, line)
        self.assertFalse(
            self.planning.coverage_gap_ids.filtered(lambda g: g.day_number == "0")
        )

    def test_02_claim_refused_on_conflict(self):
        """Approving a claim for an already assigned day raises."""
        line = self._line(self.employees[0], "0")
        line.template_id = self.template_day
        claim = self.env["hr.shift.claim"].create(
            {
                "planning_id": self.planning.id,
                "template_id": self.template_night.id,
                "day_number": "0",
                "employee_id": self.employees[0].id,
            }
        )
        with self.assertRaises(UserError):
            claim.action_approve()

    def test_03_claim_approval_needs_manager(self):
        """A regular employee cannot approve their own claim."""
        claim = (
            self.env["hr.shift.claim"]
            .with_user(self.users[0])
            .create(
                {
                    "planning_id": self.planning.id,
                    "template_id": self.template_night.id,
                    "day_number": "0",
                    "employee_id": self.employees[0].id,
                }
            )
        )
        with self.assertRaises(AccessError):
            claim.with_user(self.users[0]).action_approve()

    def test_04_swap_handover(self):
        """A hand-over moves the shift from one employee to the other."""
        self._line(self.employees[0], "1").template_id = self.template_night
        swap = self.env["hr.shift.swap"].create(
            {
                "line_id": self._line(self.employees[0], "1").id,
                "employee_id": self.employees[0].id,
                "target_employee_id": self.employees[1].id,
            }
        )
        swap.with_user(self.users[1]).action_accept()
        self.assertEqual(swap.state, "accepted")
        swap.action_approve()
        self.assertEqual(swap.state, "approved")
        self.assertFalse(self._line(self.employees[0], "1").template_id)
        self.assertEqual(
            self._line(self.employees[1], "1").template_id, self.template_night
        )

    def test_05_swap_exchange(self):
        """A two-way swap exchanges the templates of both lines."""
        line_a = self._line(self.employees[0], "2")
        line_b = self._line(self.employees[1], "2")
        line_a.template_id = self.template_night
        line_b.template_id = self.template_day
        swap = self.env["hr.shift.swap"].create(
            {
                "line_id": line_a.id,
                "employee_id": self.employees[0].id,
                "target_employee_id": self.employees[1].id,
                "target_line_id": line_b.id,
            }
        )
        swap.with_user(self.users[1]).action_accept()
        swap.action_approve()
        self.assertEqual(line_a.template_id, self.template_day)
        self.assertEqual(line_b.template_id, self.template_night)

    def test_06_swap_accept_needs_target(self):
        """Only the requested colleague may accept the swap."""
        self._line(self.employees[0], "3").template_id = self.template_night
        swap = self.env["hr.shift.swap"].create(
            {
                "line_id": self._line(self.employees[0], "3").id,
                "employee_id": self.employees[0].id,
                "target_employee_id": self.employees[1].id,
            }
        )
        with self.assertRaises(AccessError):
            swap.with_user(self.users[0]).action_accept()

    def test_07_availability_matching(self):
        """Availability matching honours the template and day wildcards."""
        availability = self.env["hr.shift.availability"].create(
            {
                "employee_id": self.employees[0].id,
                "template_id": self.template_night.id,
            }
        )
        self.assertTrue(availability._matches(self.template_night, "5"))
        self.assertFalse(availability._matches(self.template_day, "5"))
        wildcard = self.env["hr.shift.availability"].create(
            {"employee_id": self.employees[1].id}
        )
        self.assertTrue(wildcard._matches(self.template_day, "2"))
