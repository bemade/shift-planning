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
                "day_of_week_end": "1",
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

    def test_01_auto_plan_fills_all_gaps(self):
        """Both nights (Mon/Tue) get an employee; audit trail exists."""
        action = self.planning.action_auto_plan()
        self.assertEqual(action["params"]["type"], "success")
        self.assertFalse(self.planning.coverage_gap_ids)
        cascades = self.env["hr.shift.cascade"].search(
            [("planning_id", "=", self.planning.id)]
        )
        self.assertEqual(len(cascades), 2)
        self.assertEqual(set(cascades.mapped("state")), {"filled"})
        self.assertEqual(set(cascades.mapped("claim_id.state")), {"approved"})

    def test_02_unfillable_slot_reported(self):
        """A rule needing more people than exist leaves open slots."""
        self.rule.min_employees = 3
        action = self.planning.action_auto_plan()
        self.assertEqual(action["params"]["type"], "warning")
        self.assertTrue(self.planning.coverage_gap_ids)

    def test_03_spreads_load(self):
        """With one night each, the two employees share the load."""
        self.planning.action_auto_plan()
        assigned = self.planning.shift_ids.line_ids.filtered(
            lambda line: line.state == "assigned"
        )
        self.assertEqual(len(assigned.mapped("employee_id")), 2)
