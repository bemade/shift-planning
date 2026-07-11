# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.tests import TransactionCase


class TestAutoPlan(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(cls.env.context, tracking_disable=True, tz="UTC")
        )
        cls.env.user.tz = "UTC"
        cls.env.company.shift_end_day = "6"
        cls.job = cls.env["hr.job"].create({"name": "Attendant"})
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Standard", "tz": "UTC"}
        )
        cls.employees = cls.env["hr.employee"].create(
            [
                {
                    "name": f"Employee {number}",
                    "job_id": cls.job.id,
                    "resource_calendar_id": cls.calendar.id,
                    "shift_planning": True,
                }
                for number in range(2)
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
                "job_id": cls.job.id,
                "min_employees": 1,
            }
        )
        cls.planning = cls.env["hr.shift.planning"].create(
            {"year": 2030, "week_number": 10}
        )
        cls.planning.generate_shifts()

    def _assigned_days(self, employee):
        return self.planning.shift_ids.line_ids.filtered(
            lambda line: line.employee_id == employee and line.state == "assigned"
        )

    def test_01_auto_plan_fills_all_gaps(self):
        """Every night of the week gets an employee; audit trail exists."""
        action = self.planning.action_auto_plan()
        self.assertEqual(action["params"]["type"], "success")
        self.assertFalse(self.planning.coverage_gap_ids)
        cascades = self.env["hr.shift.cascade"].search(
            [("planning_id", "=", self.planning.id)]
        )
        self.assertEqual(len(cascades), 7)
        self.assertEqual(set(cascades.mapped("state")), {"filled"})
        self.assertEqual(set(cascades.mapped("claim_id.state")), {"approved"})

    def test_02_unfillable_slot_reported(self):
        """A rule needing more people than exist leaves open slots."""
        self.rule.min_employees = 3
        action = self.planning.action_auto_plan()
        self.assertEqual(action["params"]["type"], "warning")
        self.assertTrue(self.planning.coverage_gap_ids)

    def test_03_weekly_continuity_with_cap(self):
        """The same employee keeps the night shift up to 5 days, then the
        remaining days go to the next candidate (fairness cap)."""
        self.planning.action_auto_plan()
        days = sorted(len(self._assigned_days(employee)) for employee in self.employees)
        self.assertEqual(days, [2, 5])

    def test_04_uniform_week_gets_weekly_template(self):
        """A fully uniform week is grouped under its template column."""
        shift = self.planning.shift_ids.filtered(
            lambda s: s.employee_id == self.employees[0]
        )
        shift.line_ids.template_id = self.template_night
        self.planning._auto_plan_set_weekly_templates()
        self.assertEqual(shift.template_id, self.template_night)
        # and the weekly write did not regenerate the lines
        self.assertEqual(len(shift.line_ids), 7)
        self.assertEqual(
            set(shift.line_ids.mapped("template_id").ids),
            {self.template_night.id},
        )

    def test_05_continuity_beats_fairness_within_template(self):
        """Once someone starts a template, following days chain to them
        even if a colleague has fewer hours."""
        line = self.planning.shift_ids.line_ids.filtered(
            lambda line: line.employee_id == self.employees[1]
            and line.day_number == "0"
        )
        line.template_id = self.template_night
        self.planning.action_auto_plan()
        self.assertEqual(len(self._assigned_days(self.employees[1])), 5)
        self.assertEqual(len(self._assigned_days(self.employees[0])), 2)
