# Copyright 2025 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from datetime import datetime

import pytz

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form
from odoo.tools import mute_logger

from .common import TestHrShiftBase


class TestHrShift(TestHrShiftBase):
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

    def test_hr_shift_planning_display_name(self):
        self.assertEqual(
            self.planning.display_name, "2025 Week 3 (2025-01-13 - 2025-01-19)"
        )

    def test_attendance_intervals_batch(self):
        self.planning.generate_shifts()
        self.planning.shift_ids.line_ids.template_id = self.template_morning
        start_dt = end_dt = datetime(2025, 1, 13, tzinfo=pytz.utc)
        res = self.employee_a.resource_calendar_id._attendance_intervals_batch(
            start_dt, end_dt, resources=self.employee_a.resource_id
        )[self.employee_a.resource_id.id]
        interval = list(res)[0]
        start = interval[0]
        stop = interval[1]
        self.assertEqual(start.date(), fields.Date.from_string("2025-01-13"))
        self.assertEqual(start.hour, 7)
        self.assertEqual(stop.date(), fields.Date.from_string("2025-01-13"))
        self.assertEqual(stop.hour, 13)
        self.assertEqual(interval[2]._name, "hr.shift.planning.line")

    def test_hr_shift_planning_line_leave(self):
        self.env["resource.calendar.leaves"].create(
            {
                "calendar_id": self.employee_a.resource_calendar_id.id,
                "resource_id": self.employee_a.resource_id.id,
                "date_from": "2025-01-13 08:00:00",
                "date_to": "2025-01-13 17:00:00",
            }
        )
        self.planning.generate_shifts()
        shift_a = self.planning.shift_ids.filtered(
            lambda x: x.employee_id == self.employee_a
        )
        shift_a_line_0 = shift_a.line_ids.filtered(lambda x: x.day_number == "0")
        self.assertEqual(shift_a_line_0.state, "on_leave")
        self.assertFalse(shift_a_line_0.reviewed)
        self.assertTrue(self.planning.issued_shift_ids)
        shift_a.action_toggle_reviewed()
        self.assertFalse(self.planning.issued_shift_ids)
        self.assertTrue(shift_a_line_0.reviewed)
        shift_a_line_1 = shift_a.line_ids.filtered(lambda x: x.day_number == "1")
        self.assertEqual(shift_a_line_1.state, "unassigned")
        self.assertFalse(shift_a.template_id)
        self.assertFalse(shift_a_line_0.template_id)
        self.assertFalse(shift_a_line_1.template_id)
        template_morning = self.template_morning
        shift_a.write({"template_id": template_morning.id})
        self.assertEqual(shift_a.template_id, template_morning)
        self.assertFalse(shift_a_line_0.template_id)
        self.assertFalse(shift_a_line_1.exists())
        shift_a_line_1 = shift_a.line_ids.filtered(lambda x: x.day_number == "1")
        self.assertEqual(shift_a_line_1.template_id, template_morning)

    @mute_logger("odoo.models.unlink")
    def test_hr_shift_planning_full(self):
        self.assertEqual(self.planning.state, "new")
        self.planning.generate_shifts()
        self.assertEqual(self.planning.state, "assignment")
        employees = self.planning.shift_ids.mapped("employee_id")
        self.assertIn(self.employee_a, employees)
        self.assertIn(self.employee_b, employees)
        self.assertNotIn(self.employee_c, employees)
        shift_a = self.planning.shift_ids.filtered(
            lambda x: x.employee_id == self.employee_a
        )
        self.assertFalse(shift_a.template_id)
        self.assertEqual(len(shift_a.line_ids), 5)
        shift_a_line_0 = shift_a.line_ids.filtered(lambda x: x.day_number == "0")
        self.assertEqual(shift_a_line_0.state, "unassigned")
        shift_a.line_ids.template_id = self.template_morning
        self.assertEqual(shift_a_line_0.state, "assigned")
        self.assertEqual(
            shift_a_line_0.start_date, fields.Date.from_string("2025-01-13")
        )
        self.assertEqual(
            shift_a_line_0.start_time,
            fields.Datetime.from_string("2025-01-13 07:00:00"),
        )
        self.assertEqual(
            shift_a_line_0.end_time, fields.Datetime.from_string("2025-01-13 13:00:00")
        )
        shift_b = self.planning.shift_ids.filtered(
            lambda x: x.employee_id == self.employee_b
        )
        self.assertFalse(shift_b.template_id)
        self.assertEqual(len(shift_b.line_ids), 5)
        shift_b.line_ids.template_id = self.template_afternoon
        shift_b_line_0 = shift_b.line_ids.filtered(lambda x: x.day_number == "0")
        shift_b_line_0.template_id = self.template_morning
        res = self.planning.copy_to_planning()
        wizard_form = Form(self.env[res["res_model"]].with_context(**res["context"]))
        wizard = wizard_form.save()
        self.assertEqual(wizard.generation_type, "from_planning")
        self.assertEqual(wizard.from_planning_id, self.planning)
        self.assertEqual(wizard.year, 2025)
        self.assertEqual(wizard.week_number, 4)
        wizard_form = Form(self.env["shift.planning.wizard"])
        wizard_form.copy_shift_details = True
        wizard = wizard_form.save()
        self.assertEqual(wizard.generation_type, "from_last")
        self.assertEqual(wizard.from_planning_id, self.planning)
        self.assertEqual(wizard.year, 2025)
        self.assertEqual(wizard.week_number, 4)
        res = wizard.generate()
        planning_extra = self.env[res["res_model"]].browse(res["res_id"])
        self.assertTrue(planning_extra)
        self.assertEqual(planning_extra.state, "assignment")
        employees = planning_extra.shift_ids.mapped("employee_id")
        self.assertIn(self.employee_a, employees)
        self.assertIn(self.employee_b, employees)
        self.assertNotIn(self.employee_c, employees)
        shift_a = planning_extra.shift_ids.filtered(
            lambda x: x.employee_id == self.employee_a
        )
        self.assertFalse(shift_a.template_id)
        self.assertEqual(len(shift_a.line_ids), 5)
        shift_a_line_0 = shift_a.line_ids.filtered(lambda x: x.day_number == "0")
        self.assertEqual(shift_a_line_0.state, "assigned")
        self.assertEqual(shift_a_line_0.template_id, self.template_morning)
        shift_b = planning_extra.shift_ids.filtered(
            lambda x: x.employee_id == self.employee_b
        )
        self.assertFalse(shift_b.template_id)
        self.assertEqual(len(shift_b.line_ids), 5)
        shift_b_line_0 = shift_b.line_ids.filtered(lambda x: x.day_number == "0")
        self.assertEqual(shift_b_line_0.state, "assigned")
        self.assertEqual(shift_b_line_0.template_id, self.template_morning)
        shift_b_line_1 = shift_b.line_ids.filtered(lambda x: x.day_number == "1")
        self.assertEqual(shift_b_line_1.state, "assigned")
        self.assertEqual(shift_b_line_1.template_id, self.template_afternoon)


class TestHrShiftMultiLine(TestHrShiftBase):
    """Several shifts for the same employee on the same day."""

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
            lambda x: x.employee_id == cls.employee_a
        )
        cls.template_late = cls.env["hr.shift.template"].create(
            {
                "name": "Late 10-16",
                "day_of_week_start": "0",
                "day_of_week_end": "4",
                "start_time": 10,
                "end_time": 16,
                "tz": "Europe/Brussels",
            }
        )

    def _lines(self, day_number):
        return self.shift_a.line_ids.filtered(lambda x: x.day_number == day_number)

    def test_action_add_line(self):
        line = self._lines("0")
        line.template_id = self.template_morning
        extra = self.shift_a.action_add_line("0")
        self.assertEqual(extra.shift_id, self.shift_a)
        self.assertEqual(extra.day_number, "0")
        self.assertEqual(extra.state, "unassigned")
        self.assertFalse(extra.template_id)
        self.assertEqual(len(self._lines("0")), 2)
        extra.template_id = self.template_afternoon
        self.assertEqual(extra.state, "assigned")
        # An unassigned extra line can simply be removed
        second_extra = self.shift_a.action_add_line("0")
        second_extra.unlink()
        self.assertEqual(len(self._lines("0")), 2)

    def test_overlap_refused_contact_allowed(self):
        line = self._lines("0")
        line.template_id = self.template_morning  # 8-14
        extra = self.shift_a.action_add_line("0")
        with self.assertRaises(UserError) as capture, self.env.cr.savepoint():
            extra.template_id = self.template_late  # 10-16 overlaps 8-14
        message = str(capture.exception)
        self.assertIn(self.template_morning.display_name, message)
        self.assertIn(self.template_late.display_name, message)
        # Merely consecutive windows are fine (14-20 touches 8-14)
        extra.template_id = self.template_afternoon
        self.assertEqual(extra.state, "assigned")

    def test_overlap_cross_midnight_normalized(self):
        template_night = self.env["hr.shift.template"].create(
            {
                "name": "Night 22-6",
                "day_of_week_start": "0",
                "day_of_week_end": "4",
                "start_time": 22,
                "end_time": 6,
                "tz": "Europe/Brussels",
            }
        )
        line = self._lines("0")
        line.template_id = template_night  # 22-30 on the continuous scale
        extra = self.shift_a.action_add_line("0")
        # A shift within the crossing part of the night doesn't conflict:
        # it belongs to the same calendar day, before the night starts.
        extra.template_id = self.template_morning
        self.assertEqual(extra.state, "assigned")
        late_evening = self.env["hr.shift.template"].create(
            {
                "name": "Evening 20-23",
                "day_of_week_start": "0",
                "day_of_week_end": "4",
                "start_time": 20,
                "end_time": 23,
                "tz": "Europe/Brussels",
            }
        )
        another = self.shift_a.action_add_line("0")
        with self.assertRaises(UserError), self.env.cr.savepoint():
            another.template_id = late_evening  # 20-23 overlaps 22-30

    def test_overlap_across_consecutive_days(self):
        """The midnight tail of a shift conflicts with the next day's
        early shift, but not with a later one."""
        template_evening = self.env["hr.shift.template"].create(
            {
                "name": "Evening 16-0h15",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 16,
                "end_time": 0.25,
                "tz": "Europe/Brussels",
            }
        )
        template_night = self.env["hr.shift.template"].create(
            {
                "name": "Night 0-7h30",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 0,
                "end_time": 7.5,
                "tz": "Europe/Brussels",
            }
        )
        template_late_night = self.env["hr.shift.template"].create(
            {
                "name": "Night part 4-7h30",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 4,
                "end_time": 7.5,
                "tz": "Europe/Brussels",
            }
        )
        monday = self._lines("0")
        monday.template_id = template_evening  # ends Tuesday 00h15
        tuesday = self._lines("1")
        with self.assertRaises(UserError) as capture, self.env.cr.savepoint():
            tuesday.template_id = template_night  # starts Tuesday 00h00
        self.assertIn(template_evening.display_name, str(capture.exception))
        # A later shift the next day doesn't conflict with the tail
        tuesday.template_id = template_late_night
        self.assertEqual(tuesday.state, "assigned")
        # And the guard works in both directions: assigning the evening
        # after the night is refused the same way
        monday.template_id = False
        tuesday.template_id = False
        tuesday.template_id = template_night
        with self.assertRaises(UserError), self.env.cr.savepoint():
            monday.template_id = template_evening
