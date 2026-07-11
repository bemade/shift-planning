# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.tests import TransactionCase


class TestShiftSnapshot(TransactionCase):
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
                    "work_email": f"employee_{number}@test.example.com",
                }
                for number in range(2)
            ]
        )
        cls.template_day = cls.env["hr.shift.template"].create(
            {
                "name": "Day",
                "day_of_week_start": "0",
                "day_of_week_end": "6",
                "start_time": 7.0,
                "end_time": 15.0,
                "tz": "UTC",
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
        cls.line = cls._line(cls.employees[0], "0")
        cls.line.template_id = cls.template_day

    @classmethod
    def _line(cls, employee, day_number):
        return cls.planning.shift_ids.line_ids.filtered(
            lambda line: line.employee_id == employee and line.day_number == day_number
        )

    def _publish(self):
        self.planning.action_publish()
        return self.planning.publication_ids.sorted("version")[-1]

    def test_01_publish_creates_snapshot(self):
        """Publishing stores a frozen copy of the assigned lines."""
        publication = self._publish()
        self.assertEqual(publication.version, 1)
        self.assertEqual(len(publication.line_ids), 1)
        snapshot_line = publication.line_ids
        self.assertEqual(snapshot_line.employee_id, self.employees[0])
        self.assertEqual(snapshot_line.template_id, self.template_day)
        self.assertEqual(snapshot_line.template_name, self.template_day.display_name)
        # A second publication becomes version 2
        self.assertEqual(self._publish().version, 2)

    def test_02_no_variance_when_unchanged(self):
        publication = self._publish()
        publication.action_compute_variances()
        self.assertFalse(publication.variance_ids)

    def test_03_manual_change_variance(self):
        """A manual reassignment after publishing is reported as a variance."""
        publication = self._publish()
        self.line.template_id = self.template_night
        other_line = self._line(self.employees[1], "1")
        other_line.template_id = self.template_day
        publication.action_compute_variances()
        self.assertEqual(len(publication.variance_ids), 2)
        changed = publication.variance_ids.filtered(
            lambda variance: variance.employee_id == self.employees[0]
        )
        self.assertEqual(changed.published_template_id, self.template_day)
        self.assertEqual(changed.current_template_id, self.template_night)
        self.assertEqual(changed.cause, "manual")
        added = publication.variance_ids - changed
        self.assertFalse(added.published_template_id)
        self.assertEqual(added.current_template_id, self.template_day)

    def test_04_swap_variance_cause(self):
        """An approved swap is identified as the cause of its variance."""
        publication = self._publish()
        manager_group = self.env.ref("hr_shift.group_shift_manager")
        self.env.user.group_ids = [(4, manager_group.id)]
        swap = self.env["hr.shift.swap"].create(
            {
                "line_id": self.line.id,
                "employee_id": self.employees[0].id,
                "target_employee_id": self.employees[1].id,
                "planning_id": self.planning.id,
            }
        )
        swap.action_accept()
        swap.action_approve()
        publication.action_compute_variances()
        causes = set(publication.variance_ids.mapped("cause"))
        self.assertEqual(causes, {"swap"})

    def test_05_chatter_logs_change_after_publication(self):
        """Line edits after publishing are logged on the planning chatter."""
        messages_before = len(self.planning.message_ids)
        self.line.template_id = self.template_night
        self.assertEqual(
            len(self.planning.message_ids),
            messages_before,
            "No log expected before publication",
        )
        self._publish()
        messages_before = len(self.planning.message_ids)
        self.line.template_id = self.template_day
        self.assertEqual(len(self.planning.message_ids), messages_before + 1)
        self.assertIn("Change after publication", self.planning.message_ids[0].body)
