# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.tests import TransactionCase


class TestRotation(TransactionCase):
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
        cls.employees = cls.env["hr.employee"].create(
            [
                {
                    "name": f"Employee {number}",
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
        cls.rotation = cls.env["hr.shift.rotation"].create(
            {
                "name": "Week on / week off",
                "week_ids": [
                    (
                        0,
                        0,
                        {
                            "sequence": 1,
                            "name": "On",
                            "line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "day_number": str(day),
                                        "template_id": cls.template_night.id,
                                    },
                                )
                                for day in range(7)
                            ],
                        },
                    ),
                    (0, 0, {"sequence": 2, "name": "Off"}),
                ],
                "assignment_ids": [
                    (0, 0, {"employee_id": cls.employees[0].id, "offset": 0}),
                    (0, 0, {"employee_id": cls.employees[1].id, "offset": 1}),
                ],
            }
        )

    def _assigned_days(self, planning, employee):
        return len(
            planning.shift_ids.line_ids.filtered(
                lambda line: line.employee_id == employee and line.template_id
            )
        )

    def test_01_alternating_weeks(self):
        """Offsets 0/1 on a 2-week cycle make employees alternate."""
        wizard = self.env["hr.shift.rotation.apply"].create(
            {
                "rotation_id": self.rotation.id,
                "year": 2030,
                "week_from": 10,
                "week_count": 2,
            }
        )
        action = wizard.action_apply()
        plannings = (
            self.env["hr.shift.planning"]
            .browse(self.env["hr.shift.planning"].search(action["domain"]).ids)
            .sorted("week_number")
        )
        self.assertEqual(len(plannings), 2)
        week_a, week_b = plannings
        self.assertEqual(self._assigned_days(week_a, self.employees[0]), 7)
        self.assertEqual(self._assigned_days(week_a, self.employees[1]), 0)
        self.assertEqual(self._assigned_days(week_b, self.employees[0]), 0)
        self.assertEqual(self._assigned_days(week_b, self.employees[1]), 7)

    def test_02_no_overwrite_by_default(self):
        """Existing assignments are preserved without the overwrite flag."""
        template_day = self.env["hr.shift.template"].create(
            {
                "name": "Day",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 7.0,
                "end_time": 15.0,
                "tz": "UTC",
            }
        )
        planning = self.env["hr.shift.planning"].create(
            {"year": 2030, "week_number": 10}
        )
        planning.generate_shifts()
        line = planning.shift_ids.line_ids.filtered(
            lambda line: line.employee_id == self.employees[0]
            and line.day_number == "0"
        )
        line.template_id = template_day
        self.env["hr.shift.rotation.apply"].create(
            {
                "rotation_id": self.rotation.id,
                "year": 2030,
                "week_from": 10,
                "week_count": 1,
            }
        ).action_apply()
        self.assertEqual(line.template_id, template_day)
