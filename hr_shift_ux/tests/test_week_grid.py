# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import re

from odoo.tests import TransactionCase


class TestWeekGridOrder(TransactionCase):
    def _column_order(self):
        arch = self.env["hr.shift.planning"].get_view(view_type="form")["arch"]
        return [int(number) for number in re.findall(r'name="day_code_(\d)"', arch)]

    def test_day_columns_follow_week_start(self):
        lang = self.env["res.lang"]._lang_get(self.env.user.lang or "en_US")
        lang.week_start = "1"
        self.assertEqual(self._column_order(), [0, 1, 2, 3, 4, 5, 6])
        lang.week_start = "7"
        self.assertEqual(self._column_order(), [6, 0, 1, 2, 3, 4, 5])


class TestDayCodes(TransactionCase):
    def test_day_codes_join_multiple_shifts(self):
        """Two shifts the same day render as joined codes (Ja+N)."""
        self.env.user.tz = self.env.user.tz or "UTC"
        self.env.company.shift_end_day = "6"
        calendar = self.env["resource.calendar"].create(
            {"name": "Standard", "tz": "UTC"}
        )
        employee = self.env["hr.employee"].create(
            {
                "name": "Day codes employee",
                "resource_calendar_id": calendar.id,
                "shift_planning": True,
            }
        )
        template_day, template_night = self.env["hr.shift.template"].create(
            [
                {
                    "name": "Ja 7h30-14h30",
                    "day_of_week_start": "0",
                    "day_of_week_end": "6",
                    "start_time": 7.5,
                    "end_time": 14.5,
                    "tz": "UTC",
                },
                {
                    "name": "N part 00h-04h",
                    "day_of_week_start": "0",
                    "day_of_week_end": "6",
                    "start_time": 0.0,
                    "end_time": 4.0,
                    "tz": "UTC",
                },
            ]
        )
        planning = self.env["hr.shift.planning"].create(
            {"year": 2030, "week_number": 30}
        )
        planning.generate_shifts()
        shift = planning.shift_ids.filtered(lambda item: item.employee_id == employee)
        shift.line_ids.filtered(
            lambda line: line.day_number == "0"
        ).template_id = template_day
        extra = shift.action_add_line("0")
        extra.template_id = template_night
        self.assertEqual(shift.day_code_0, "Ja+N")
        self.assertEqual(shift.day_code_1, "")
