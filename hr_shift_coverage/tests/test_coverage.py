# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.tests import TransactionCase


class TestShiftCoverage(TransactionCase):
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
        cls.job_nurse = cls.env["hr.job"].create({"name": "Auxiliary Nurse"})
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Standard 40h", "tz": "UTC"}
        )
        cls.employees = cls.env["hr.employee"].create(
            [
                {
                    "name": f"Employee {number}",
                    "job_id": job.id,
                    "resource_calendar_id": cls.calendar.id,
                    "shift_planning": True,
                }
                for number, job in enumerate(
                    [cls.job_attendant, cls.job_attendant, cls.job_nurse]
                )
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
        cls.planning = cls.env["hr.shift.planning"].create(
            {"year": 2030, "week_number": 10}
        )
        cls.planning.generate_shifts()

    def _assign(self, employee):
        shift = self.planning.shift_ids.filtered(lambda s: s.employee_id == employee)
        shift.line_ids.template_id = self.template_night

    def test_01_gap_detection_with_job(self):
        """A rule requiring 2 attendants reports gaps until both assigned."""
        self.env["hr.shift.coverage.rule"].create(
            {
                "template_id": self.template_night.id,
                "job_id": self.job_attendant.id,
                "min_employees": 2,
            }
        )
        self.planning._update_coverage_gaps()
        gaps = self.planning.coverage_gap_ids
        self.assertEqual(len(gaps), 7, "One gap per weekday expected")
        self.assertEqual(set(gaps.mapped("missing")), {2})
        # Assign one attendant: still one missing per day
        self._assign(self.employees[0])
        self.planning._update_coverage_gaps()
        gaps = self.planning.coverage_gap_ids
        self.assertEqual(len(gaps), 7)
        self.assertEqual(set(gaps.mapped("missing")), {1})
        self.assertEqual(set(gaps.mapped("assigned")), {1})
        # The nurse does not count towards the attendant rule
        self._assign(self.employees[2])
        self.planning._update_coverage_gaps()
        self.assertEqual(set(self.planning.coverage_gap_ids.mapped("missing")), {1})
        # Assign the second attendant: coverage complete
        self._assign(self.employees[1])
        self.planning._update_coverage_gaps()
        self.assertFalse(self.planning.coverage_gap_ids)

    def test_02_rule_without_job_counts_anyone(self):
        """A jobless rule is satisfied by any assigned employee."""
        self.env["hr.shift.coverage.rule"].create(
            {"template_id": self.template_night.id, "min_employees": 1}
        )
        self.planning._update_coverage_gaps()
        self.assertEqual(len(self.planning.coverage_gap_ids), 7)
        self._assign(self.employees[2])
        self.planning._update_coverage_gaps()
        self.assertFalse(self.planning.coverage_gap_ids)

    def test_03_gap_dates_follow_planning_week(self):
        """Gap dates are derived from the planning start date."""
        self.env["hr.shift.coverage.rule"].create(
            {"template_id": self.template_night.id, "min_employees": 1}
        )
        self.planning._update_coverage_gaps()
        dates = self.planning.coverage_gap_ids.mapped("date")
        self.assertEqual(len(set(dates)), 7)
        self.assertEqual(min(dates), self.planning.start_date)

    def test_04_action_notification_when_covered(self):
        """The check action returns a notification when nothing is missing."""
        action = self.planning.action_check_coverage()
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "display_notification")
