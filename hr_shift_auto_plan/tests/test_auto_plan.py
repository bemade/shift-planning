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

    def _line_of(self, employee, day_number):
        return self.planning.shift_ids.line_ids.filtered(
            lambda line: line.employee_id == employee and line.day_number == day_number
        )

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

    def test_06_auto_plan_avoids_overtime(self):
        """A candidate at their contract hours loses to a lighter one."""
        # Contract of 16h/week: two attendances of 8h
        small = self.env["resource.calendar"].create(
            {
                "name": "Part time 16h",
                "tz": "UTC",
                "attendance_ids": [
                    (5, 0, 0),
                    (
                        0,
                        0,
                        {
                            "name": "Mon",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 16,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": "Tue",
                            "dayofweek": "1",
                            "hour_from": 8,
                            "hour_to": 16,
                        },
                    ),
                ],
            }
        )
        self.employees[0].resource_calendar_id = small
        self.planning.action_auto_plan()
        days_first = len(self._assigned_days(self.employees[0]))
        # 8h nights: at most 2 fit in a 16h contract
        self.assertLessEqual(
            days_first, 2, "The planner must stop at the contract hours"
        )
        self.assertEqual(
            self.planning.coverage_gap_ids.ids,
            [],
            "The other employee absorbs the remaining nights",
        )

    def test_07_overload_is_last_resort_and_logged(self):
        """With nobody light enough, the slot is still filled and logged."""
        small = self.env["resource.calendar"].create(
            {
                "name": "Part time 8h",
                "tz": "UTC",
                "attendance_ids": [
                    (5, 0, 0),
                    (
                        0,
                        0,
                        {
                            "name": "Mon",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 16,
                        },
                    ),
                ],
            }
        )
        self.employees.resource_calendar_id = small
        action = self.planning.action_auto_plan()
        self.assertEqual(
            self.planning.coverage_gap_ids.ids,
            [],
            "Coverage still comes first: every night is filled",
        )
        self.assertIn("exceed contract hours", action["params"]["message"])
        overload_logs = self.env["mail.message"].search(
            [
                ("model", "=", "hr.shift.cascade"),
                ("body", "like", "beyond their contract hours"),
            ]
        )
        self.assertTrue(overload_logs, "Each overload is logged on its cascade")

    def test_08_last_resort_picks_smallest_overshoot(self):
        """When everyone exceeds, the least-hurt candidate is chosen."""
        cal8 = self.env["resource.calendar"].create(
            {
                "name": "8h",
                "tz": "UTC",
                "attendance_ids": [
                    (5, 0, 0),
                    (
                        0,
                        0,
                        {
                            "name": "Mon",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 16,
                        },
                    ),
                ],
            }
        )
        cal4 = self.env["resource.calendar"].create(
            {
                "name": "4h",
                "tz": "UTC",
                "attendance_ids": [
                    (5, 0, 0),
                    (
                        0,
                        0,
                        {
                            "name": "Mon",
                            "dayofweek": "0",
                            "hour_from": 8,
                            "hour_to": 12,
                        },
                    ),
                ],
            }
        )
        self.employees[0].resource_calendar_id = cal8
        self.employees[1].resource_calendar_id = cal4
        for employee in self.employees:
            self._line_of(employee, "0").template_id = self.template_night
        cascade = self.env["hr.shift.cascade"].create(
            {
                "planning_id": self.planning.id,
                "template_id": self.template_night.id,
                "day_number": "1",
                "rule_id": self.rule.id,
            }
        )
        cascade.action_generate_candidates()
        candidate, overshoot = self.planning._auto_plan_pick(cascade)
        self.assertEqual(
            candidate.employee_id, self.employees[0], "8h overshoot beats 12h overshoot"
        )
        self.assertAlmostEqual(overshoot, 8.0, places=2)
