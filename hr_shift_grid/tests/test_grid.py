# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.hr_shift.tests.common import TestHrShiftBase


@tagged("post_install", "-at_install")
class TestShiftGrid(TestHrShiftBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.planning = cls.env["hr.shift.planning"].create(
            {
                "year": 2025,
                "week_number": 3,
                "start_date": "2025-01-13",
                "end_date": "2025-01-19",
            }
        )
        cls.planning.generate_shifts()
        cls.shift_a = cls.planning.shift_ids.filtered(
            lambda s: s.employee_id == cls.employee_a
        )
        cls.shift_b = cls.planning.shift_ids.filtered(
            lambda s: s.employee_id == cls.employee_b
        )
        cls.template_night = cls.env["hr.shift.template"].create(
            {
                "name": "Night 22-6",
                "day_of_week_start": "0",
                "day_of_week_end": "4",
                "start_time": 22,
                "end_time": 6,
                "tz": "Europe/Brussels",
            }
        )
        cls.lang = cls.env["res.lang"]._lang_get(cls.env.user.lang or "en_US")

    def _line(self, shift, day_number):
        return shift.line_ids.filtered(lambda line: line.day_number == day_number)

    def test_grid_data_structure(self):
        self.lang.week_start = "1"  # Monday first
        data = self.planning.grid_data()
        self.assertEqual(data["planning_id"], self.planning.id)
        self.assertEqual(
            [day["day_number"] for day in data["days"]],
            ["0", "1", "2", "3", "4", "5", "6"],
        )
        self.assertEqual(data["days"][0]["date"], "2025-01-13")
        self.assertEqual(data["days"][6]["date"], "2025-01-19")
        employees = [
            employee for group in data["groups"] for employee in group["employees"]
        ]
        self.assertEqual(
            {employee["employee_id"] for employee in employees},
            set(self.planning.shift_ids.employee_id.ids),
        )
        # Monday to friday have lines (company shift days), each unassigned
        employee_a_data = next(
            employee
            for employee in employees
            if employee["employee_id"] == self.employee_a.id
        )
        self.assertEqual(set(employee_a_data["cells"]), {"0", "1", "2", "3", "4"})
        self.assertEqual(employee_a_data["cells"]["0"]["state"], "unassigned")
        template_codes = {
            template["id"]: template["code"] for template in data["templates"]
        }
        self.assertEqual(template_codes[self.template_morning.id], "Morning")
        self.assertEqual(template_codes[self.template_night.id], "Night")

    def test_grid_data_week_start_sunday(self):
        self.lang.week_start = "7"  # Sunday first, like fr_CA
        data = self.planning.grid_data()
        self.assertEqual(
            [day["day_number"] for day in data["days"]],
            ["6", "0", "1", "2", "3", "4", "5"],
        )
        self.assertEqual(data["days"][0]["date"], "2025-01-19")

    def test_grid_write_and_hours(self):
        line = self._line(self.shift_a, "0")
        data = self.planning.grid_write(line.id, self.template_morning.id)
        self.assertEqual(line.template_id, self.template_morning)
        employee_a_data = next(
            employee
            for group in data["groups"]
            for employee in group["employees"]
            if employee["employee_id"] == self.employee_a.id
        )
        self.assertEqual(employee_a_data["cells"]["0"]["state"], "assigned")
        self.assertEqual(
            employee_a_data["cells"]["0"]["template_id"], self.template_morning.id
        )
        self.assertEqual(employee_a_data["hours"], 6.0)  # 8 -> 14
        self.assertEqual(data["day_counts"]["0"], 1)
        # Unassign
        data = self.planning.grid_write(line.id, False)
        self.assertFalse(line.template_id)
        self.assertEqual(data["day_counts"]["0"], 0)

    def test_grid_hours_cross_midnight_normalized(self):
        line = self._line(self.shift_a, "1")
        data = self.planning.grid_write(line.id, self.template_night.id)
        self.assertLess(line.duration_hours, 0)  # raw duration is negative
        employee_a_data = next(
            employee
            for group in data["groups"]
            for employee in group["employees"]
            if employee["employee_id"] == self.employee_a.id
        )
        self.assertEqual(employee_a_data["hours"], 8.0)  # 22 -> 6 = 8h

    def test_grid_swap_between_employees(self):
        line_a = self._line(self.shift_a, "0")
        line_b = self._line(self.shift_b, "0")
        self.planning.grid_write(line_a.id, self.template_morning.id)
        self.planning.grid_write(line_b.id, self.template_afternoon.id)
        self.planning.grid_swap(line_a.id, line_b.id)
        self.assertEqual(line_a.template_id, self.template_afternoon)
        self.assertEqual(line_b.template_id, self.template_morning)

    def test_grid_swap_to_empty_cell_moves(self):
        line_a = self._line(self.shift_a, "0")
        line_b = self._line(self.shift_b, "0")
        self.planning.grid_write(line_a.id, self.template_morning.id)
        self.planning.grid_swap(line_a.id, line_b.id)
        self.assertFalse(line_a.template_id)
        self.assertEqual(line_b.template_id, self.template_morning)

    def test_grid_write_on_leave_refused(self):
        self.env["resource.calendar.leaves"].create(
            {
                "calendar_id": self.employee_a.resource_calendar_id.id,
                "resource_id": self.employee_a.resource_id.id,
                "date_from": "2025-01-13 08:00:00",
                "date_to": "2025-01-13 17:00:00",
            }
        )
        self.planning.regenerate_shifts()
        shift_a = self.planning.shift_ids.filtered(
            lambda s: s.employee_id == self.employee_a
        )
        line = self._line(shift_a, "0")
        self.assertEqual(line.state, "on_leave")
        with self.assertRaises(UserError):
            self.planning.grid_write(line.id, self.template_morning.id)
        with self.assertRaises(UserError):
            other = self._line(shift_a, "1")
            self.planning.grid_swap(other.id, line.id)

    def test_grid_line_from_other_planning_refused(self):
        other_planning = self.env["hr.shift.planning"].create(
            {
                "year": 2025,
                "week_number": 4,
                "start_date": "2025-01-20",
                "end_date": "2025-01-26",
            }
        )
        other_planning.generate_shifts()
        foreign_line = other_planning.shift_ids.line_ids[0]
        with self.assertRaises(UserError):
            self.planning.grid_write(foreign_line.id, self.template_morning.id)

    def test_open_grid_action(self):
        action = self.planning.action_open_grid()
        self.assertEqual(action["tag"], "hr_shift_grid.action")
        self.assertEqual(action["params"]["planning_id"], self.planning.id)
