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
