# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.tests import TransactionCase


class TestWorkload(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context=dict(cls.env.context, tracking_disable=True, tz="UTC")
        )
        cls.env.user.tz = "UTC"
        cls.env.company.shift_end_day = "6"
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "16h/week",
                "tz": "UTC",
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Attendance",
                            "dayofweek": str(day),
                            "hour_from": 8,
                            "hour_to": 16,
                        },
                    )
                    for day in range(2)
                ],
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Employee",
                "resource_calendar_id": cls.calendar.id,
                "shift_planning": True,
            }
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
        cls.shift = cls.planning.shift_ids

    def test_01_planned_hours_normalized(self):
        """Two 8h night shifts (crossing midnight) count as 16h."""
        for day in ("0", "1"):
            self.shift.line_ids.filtered(
                lambda line, day=day: line.day_number == day
            ).template_id = self.template_night
        self.assertEqual(self.shift.planned_hours, 16)
        self.assertEqual(self.shift.allocated_hours, 16)
        self.assertFalse(self.shift.overtime)

    def test_02_overtime_flag(self):
        """A third night pushes the employee over their 16h schedule."""
        for day in ("0", "1", "2"):
            self.shift.line_ids.filtered(
                lambda line, day=day: line.day_number == day
            ).template_id = self.template_night
        self.assertEqual(self.shift.planned_hours, 24)
        self.assertTrue(self.shift.overtime)
        self.assertEqual(self.planning.overtime_count, 1)
