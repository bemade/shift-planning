# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models
from odoo.exceptions import UserError


def _format_time(value):
    hours = int(value) % 24
    minutes = round((value - int(value)) * 60)
    return f"{hours:02d}h{minutes:02d}"


class HrShiftTemplate(models.Model):
    _inherit = "hr.shift.template"

    parent_template_id = fields.Many2one(
        comodel_name="hr.shift.template",
        ondelete="set null",
        index=True,
        help="Full shift this partial shift is a part of.",
    )
    child_template_ids = fields.One2many(
        comodel_name="hr.shift.template",
        inverse_name="parent_template_id",
    )

    def _normalized_end(self):
        """End time on a continuous scale (end past midnight gets +24)."""
        self.ensure_one()
        if self.end_time <= self.start_time:
            return self.end_time + 24
        return self.end_time

    def _split_pairs(self):
        """[(first part, second part), ...] — children pairs that exactly
        partition this template's time window."""
        self.ensure_one()
        pairs = []
        for first in self.child_template_ids.filtered(
            lambda child: child.start_time == self.start_time
        ):
            mate = self.child_template_ids.filtered(
                lambda child, first=first: (
                    child.start_time == first.end_time
                    and child.end_time == self.end_time
                )
            )
            if mate:
                pairs.append((first, mate[0]))
        return pairs

    def _get_or_create_split_pair(self, cut_time):
        """Return (first, second) child templates cutting this shift at
        ``cut_time``, reusing existing children when they exist."""
        self.ensure_one()
        if self.parent_template_id:
            raise UserError(self.env._("A partial shift cannot be split again."))
        cut = cut_time % 24
        window_start, window_end = self.start_time, self._normalized_end()
        normalized_cut = cut if cut > window_start else cut + 24
        if not window_start < normalized_cut < window_end:
            raise UserError(
                self.env._(
                    "The cut time must fall strictly inside the shift "
                    "(%(start)s to %(end)s).",
                    start=_format_time(self.start_time),
                    end=_format_time(self.end_time),
                )
            )
        common = {
            "day_of_week_start": self.day_of_week_start,
            "day_of_week_end": self.day_of_week_end,
            "tz": self.tz,
            "parent_template_id": self.id,
        }
        parts = []
        for start, end in (
            (self.start_time, cut),
            (cut, self.end_time),
        ):
            existing = self.child_template_ids.filtered(
                lambda child, start=start, end=end: (
                    child.start_time == start and child.end_time == end
                )
            )
            if existing:
                parts.append(existing[0])
                continue
            parts.append(
                self.create(
                    {
                        **common,
                        "name": self.env._(
                            "%(parent)s — part %(start)s-%(end)s",
                            parent=self.name,
                            start=_format_time(start),
                            end=_format_time(end),
                        ),
                        "start_time": start,
                        "end_time": end,
                    }
                )
            )
        return parts[0], parts[1]
