# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.tests import TransactionCase


class TestTimeline(TransactionCase):
    def test_01_timeline_view_validates(self):
        """The timeline view loads and validates against the model."""
        view = self.env.ref("hr_shift_timeline.shift_planning_line_timeline")
        fields_view = self.env["hr.shift.planning.line"].get_view(view.id)
        self.assertEqual(fields_view["arch"][:9], "<timeline")
