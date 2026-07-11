# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models


class HrShiftCoverageRule(models.Model):
    _inherit = "hr.shift.coverage.rule"

    def _covering_line_count(self, lines, day_number):
        """A pair of assigned split parts counts as one employee covering
        the parent shift."""
        count = super()._covering_line_count(lines, day_number)
        for first, second in self.template_id._split_pairs():
            count += min(
                len(self._filter_rule_lines(lines, first, day_number)),
                len(self._filter_rule_lines(lines, second, day_number)),
            )
        return count
