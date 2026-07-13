# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestShiftCascade(TransactionCase):
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
        cls.attendants = cls.env["hr.employee"].create(
            [
                {
                    "name": f"Attendant {number}",
                    "job_id": cls.job_attendant.id,
                    "resource_calendar_id": cls.calendar.id,
                    "shift_planning": True,
                }
                for number in range(3)
            ]
        )
        cls.nurse = cls.env["hr.employee"].create(
            {
                "name": "Nurse",
                "job_id": cls.job_nurse.id,
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
        cls.rule = cls.env["hr.shift.coverage.rule"].create(
            {
                "template_id": cls.template_night.id,
                "job_id": cls.job_attendant.id,
                "min_employees": 1,
            }
        )
        cls.planning = cls.env["hr.shift.planning"].create(
            {"year": 2030, "week_number": 10}
        )
        cls.planning.generate_shifts()

    def _line(self, employee, day_number):
        return self.planning.shift_ids.line_ids.filtered(
            lambda line: line.employee_id == employee and line.day_number == day_number
        )

    def _launch(self, day_number="0"):
        self.planning._update_coverage_gaps()
        gap = self.planning.coverage_gap_ids.filtered(
            lambda g: g.day_number == day_number
        )
        action = gap.action_launch_cascade()
        return self.env["hr.shift.cascade"].browse(action["res_id"])

    def test_01_candidates_filtered_and_ordered(self):
        """Only free, job-matching employees; fewest week hours first."""
        # Attendant 2 already works 3 nights that week: ranked last
        for day in ("1", "2", "3"):
            self._line(self.attendants[2], day).template_id = self.template_night
        cascade = self._launch("0")
        candidates = cascade.candidate_ids
        # The nurse is excluded by the rule's job position
        self.assertNotIn(self.nurse, candidates.mapped("employee_id"))
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[-1].employee_id, self.attendants[2])
        self.assertGreater(candidates[-1].week_hours, 0)

    def test_02_availability_filter(self):
        """An employee who declared other availabilities is excluded."""
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
        self.env["hr.shift.availability"].create(
            {
                "employee_id": self.attendants[0].id,
                "template_id": template_day.id,
            }
        )
        cascade = self._launch("0")
        self.assertNotIn(
            self.attendants[0], cascade.candidate_ids.mapped("employee_id")
        )

    def test_03_accept_fills_slot(self):
        """Acceptance assigns the line, closes the gap, skips the rest."""
        cascade = self._launch("0")
        cascade.action_start()
        first = cascade.candidate_ids[0]
        first.action_accept()
        self.assertEqual(cascade.state, "filled")
        self.assertEqual(cascade.claim_id.state, "approved")
        line = self._line(first.employee_id, "0")
        self.assertEqual(line.template_id, self.template_night)
        self.assertTrue(
            all(
                candidate.state == "skipped"
                for candidate in cascade.candidate_ids - first
            )
        )
        self.planning._update_coverage_gaps()
        self.assertFalse(
            self.planning.coverage_gap_ids.filtered(lambda g: g.day_number == "0")
        )

    def test_04_exhausted_when_all_decline(self):
        """The cascade escalates when every candidate declines."""
        cascade = self._launch("0")
        cascade.action_start()
        for candidate in cascade.candidate_ids:
            candidate.action_decline()
        self.assertEqual(cascade.state, "exhausted")

    def test_05_fairness_rotation(self):
        """A recently offered employee is ranked after an equal peer."""
        first_cascade = self._launch("0")
        first_cascade.action_start()
        contacted = first_cascade.candidate_ids[0]
        contacted.action_decline()
        contacted_employee = contacted.employee_id
        second_cascade = self._launch("1")
        candidates = second_cascade.candidate_ids
        self.assertEqual(candidates[-1].employee_id, contacted_employee)

    def test_06_start_requires_candidates(self):
        """Starting a cascade with no eligible candidate raises."""
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
        # Every attendant declares availability for day shifts only
        self.env["hr.shift.availability"].create(
            [
                {
                    "employee_id": attendant.id,
                    "template_id": template_day.id,
                }
                for attendant in self.attendants
            ]
        )
        cascade = self._launch("0")
        self.assertFalse(cascade.candidate_ids)
        with self.assertRaises(UserError):
            cascade.action_start()

    def _create_day_template(self, name="Day", start=7.0, end=15.0):
        return self.env["hr.shift.template"].create(
            {
                "name": name,
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": start,
                "end_time": end,
                "tz": "UTC",
            }
        )

    def test_07_busy_employees_ranked_after_free(self):
        """Employees already working that day come after the free ones."""
        template_day = self._create_day_template()
        self._line(self.attendants[0], "0").template_id = template_day
        cascade = self._launch("0")
        candidates = cascade.candidate_ids
        self.assertEqual(len(candidates), 3)
        busy = candidates[-1]
        self.assertEqual(busy.employee_id, self.attendants[0])
        self.assertTrue(busy.is_extra_line)
        self.assertFalse(busy.line_id)
        self.assertFalse(any(candidates[:-1].mapped("is_extra_line")))

    def test_08_busy_overlapping_excluded(self):
        """A busy employee whose shift overlaps the slot is not called."""
        template_evening = self._create_day_template("Evening", 15.0, 23.5)
        self._line(self.attendants[0], "0").template_id = template_evening
        cascade = self._launch("0")  # Night 23-7 overlaps evening until 23.5
        self.assertNotIn(
            self.attendants[0], cascade.candidate_ids.mapped("employee_id")
        )

    def test_09_busy_accept_creates_extra_line(self):
        """Acceptance by a busy employee adds and assigns an extra line."""
        template_day = self._create_day_template()
        day_line = self._line(self.attendants[0], "0")
        day_line.template_id = template_day
        cascade = self._launch("0")
        cascade.action_start()
        busy = cascade.candidate_ids.filtered("is_extra_line")
        self.assertEqual(busy.employee_id, self.attendants[0])
        busy.action_accept()
        self.assertEqual(cascade.state, "filled")
        self.assertEqual(cascade.claim_id.state, "approved")
        lines = self._line(self.attendants[0], "0")
        self.assertEqual(len(lines), 2)
        extra = lines - day_line
        self.assertEqual(extra.template_id, self.template_night)
        self.assertEqual(busy.line_id, extra)
        self.assertEqual(cascade.claim_id.line_id, extra)
        self.assertEqual(day_line.template_id, template_day)
