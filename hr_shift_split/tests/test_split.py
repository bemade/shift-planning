# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestShiftSplit(TransactionCase):
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
            {"name": "Standard 40h", "tz": "UTC"}
        )
        cls.employees = cls.env["hr.employee"].create(
            [
                {
                    "name": f"Employee {number}",
                    "job_id": cls.job.id,
                    "resource_calendar_id": cls.calendar.id,
                    "shift_planning": True,
                }
                for number in range(3)
            ]
        )
        cls.template_evening = cls.env["hr.shift.template"].create(
            {
                "name": "Evening",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 16.0,
                "end_time": 0.25,
                "tz": "UTC",
            }
        )
        cls.rule = cls.env["hr.shift.coverage.rule"].create(
            {
                "template_id": cls.template_evening.id,
                "job_id": cls.job.id,
                "min_employees": 1,
            }
        )
        cls.planning = cls.env["hr.shift.planning"].create(
            {"year": 2030, "week_number": 10}
        )
        cls.planning.generate_shifts()
        cls.line = cls._line(cls.employees[0], "0")
        cls.line.template_id = cls.template_evening

    @classmethod
    def _line(cls, employee, day_number):
        return cls.planning.shift_ids.line_ids.filtered(
            lambda line: line.employee_id == employee and line.day_number == day_number
        )

    def _gap(self):
        self.planning._update_coverage_gaps()
        return self.planning.coverage_gap_ids.filtered(
            lambda gap: gap.day_number == "0"
        )

    def test_01_split_pair_creation_and_reuse(self):
        """Splitting a cross-midnight shift yields two linked parts."""
        first, second = self.template_evening._get_or_create_split_pair(20.0)
        self.assertEqual((first.start_time, first.end_time), (16.0, 20.0))
        self.assertEqual((second.start_time, second.end_time), (20.0, 0.25))
        self.assertEqual(first.parent_template_id, self.template_evening)
        self.assertEqual(second.parent_template_id, self.template_evening)
        again = self.template_evening._get_or_create_split_pair(20.0)
        self.assertEqual((first, second), again, "Existing parts must be reused")
        self.assertEqual(self.template_evening._split_pairs(), [(first, second)])

    def test_02_invalid_cut_raises(self):
        with self.assertRaises(UserError):
            self.template_evening._get_or_create_split_pair(15.0)
        with self.assertRaises(UserError):
            self.template_evening._get_or_create_split_pair(16.0)
        first, _second = self.template_evening._get_or_create_split_pair(20.0)
        with self.assertRaises(UserError):
            first._get_or_create_split_pair(18.0)

    def test_03_coverage_counts_assigned_pair(self):
        """Two assigned parts cover the parent rule; one alone does not."""
        first, second = self.template_evening._get_or_create_split_pair(20.0)
        self.assertFalse(self._gap(), "Full shift assigned: no gap expected")
        self.line.template_id = False
        self.assertTrue(self._gap(), "Freed shift must open a gap")
        self._line(self.employees[1], "0").template_id = first
        gap = self._gap()
        self.assertTrue(gap, "Half a split does not cover the shift")
        self.assertEqual(gap.assigned, 0)
        self._line(self.employees[2], "0").template_id = second
        self.assertFalse(self._gap(), "Both parts assigned: shift covered")

    def test_04_wizard_from_line(self):
        """The wizard frees the line and prepares the two parts."""
        wizard = self.env["hr.shift.split.wizard"].create(
            {"line_id": self.line.id, "cut_time": 20.0}
        )
        self.assertEqual(wizard.template_id, self.template_evening)
        result = wizard.action_split()
        self.assertFalse(self.line.template_id)
        pairs = self.template_evening._split_pairs()
        self.assertEqual(len(pairs), 1)
        if "hr.shift.cascade" in self.env:
            cascades = self.env["hr.shift.cascade"].search(result["domain"])
            self.assertEqual(len(cascades), 2)
            self.assertEqual(
                set(cascades.mapped("template_id.id")),
                {pairs[0][0].id, pairs[0][1].id},
            )
            for cascade in cascades:
                self.assertEqual(cascade.rule_id, self.rule)
                self.assertEqual(
                    set(cascade.candidate_ids.mapped("employee_id")),
                    set(self.employees[1:]),
                    "Only employees free that day are candidates",
                )

    def test_05_wizard_from_gap(self):
        self.line.template_id = False
        gap = self._gap()
        action = gap.action_open_split_wizard()
        wizard = (
            self.env["hr.shift.split.wizard"]
            .with_context(**action["context"])
            .create({"cut_time": 20.0, "gap_id": gap.id})
        )
        wizard.action_split()
        pairs = self.template_evening._split_pairs()
        self.assertEqual(len(pairs), 1)

    def test_06_busy_employee_takes_part(self):
        """End to end: an employee already working that day accepts a
        part, on an extra line, and both halves close the gap."""
        if "hr.shift.cascade" not in self.env:
            self.skipTest("hr_shift_cascade is not installed")
        template_morning = self.env["hr.shift.template"].create(
            {
                "name": "Morning",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 6.0,
                "end_time": 12.0,
                "tz": "UTC",
            }
        )
        morning_line = self._line(self.employees[1], "0")
        morning_line.template_id = template_morning
        wizard = self.env["hr.shift.split.wizard"].create(
            {"line_id": self.line.id, "cut_time": 20.0}
        )
        result = wizard.action_split()
        cascades = self.env["hr.shift.cascade"].search(result["domain"])
        first_part = cascades.filtered(
            lambda cascade: cascade.template_id.start_time == 16.0
        )
        second_part = cascades - first_part
        # The busy employee is called on both parts, after the free ones
        busy = first_part.candidate_ids.filtered("is_extra_line")
        self.assertEqual(busy.employee_id, self.employees[1])
        self.assertEqual(first_part.candidate_ids[-1], busy)
        first_part.action_start()
        busy.action_accept()
        lines = self._line(self.employees[1], "0")
        self.assertEqual(len(lines), 2)
        self.assertEqual((lines - morning_line).template_id, first_part.template_id)
        self.assertEqual(morning_line.template_id, template_morning)
        # A free employee takes the other half: the gap is closed
        second_part.action_start()
        second_part.candidate_ids.filtered(
            lambda candidate: not candidate.is_extra_line
        )[0].action_accept()
        self.assertFalse(self._gap(), "Both parts assigned: shift covered")
