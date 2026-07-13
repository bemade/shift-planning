# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date


class ShiftPlanning(models.Model):
    _inherit = "hr.shift.planning"

    def action_open_grid(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "hr_shift_grid.action",
            "name": self.env._(
                "Interactive grid — %(planning)s", planning=self.display_name
            ),
            "params": {"planning_id": self.id},
        }

    # ------------------------------------------------------------------
    # Grid API: everything the client displays comes from grid_data() and
    # every change goes through grid_write() / grid_swap(), which return a
    # fresh grid_data() so the client never computes anything itself.
    # ------------------------------------------------------------------

    def grid_data(self):
        self.ensure_one()
        lang = self.env["res.lang"]._lang_get(self.env.user.lang or "en_US")
        # res.lang week_start: 1 = Monday .. 7 = Sunday.
        # hr_shift day_number: "0" = Monday .. "6" = Sunday.
        first_day = (int(lang.week_start or "1") - 1) % 7
        today = fields.Date.context_today(self)
        days = []
        for offset in range(7):
            number = (first_day + offset) % 7
            day_date = self.start_date + timedelta(days=number)
            days.append(
                {
                    "day_number": str(number),
                    "label": format_date(self.env, day_date, date_format="EEEE"),
                    "date": fields.Date.to_string(day_date),
                    "date_label": format_date(self.env, day_date, date_format="d MMM"),
                    "is_today": day_date == today,
                }
            )
        # Shift templates are a small, bounded configuration table
        templates = self.env["hr.shift.template"].search([])  # pylint: disable=no-search-all
        groups = {}
        day_counts = dict.fromkeys((str(number) for number in range(7)), 0)
        for shift in self.shift_ids.sorted(lambda s: s.employee_id.name or ""):
            department = shift.employee_id.department_id
            group = groups.setdefault(
                department.id or 0,
                {
                    "id": department.id or 0,
                    "name": department.name or self.env._("No department"),
                    "employees": [],
                },
            )
            cells = {}
            total_hours = 0.0
            for line in shift.line_ids:
                template = line.template_id
                cells[line.day_number] = {
                    "line_id": line.id,
                    "template_id": template.id or False,
                    "code": self._grid_template_code(template),
                    "color": template.color or 0,
                    "state": line.state,
                }
                if line.state == "assigned" and template:
                    duration = line.duration_hours
                    if duration < 0:  # shift crossing midnight
                        duration += 24
                    total_hours += duration
                    day_counts[line.day_number] += 1
            group["employees"].append(
                {
                    "employee_id": shift.employee_id.id,
                    "name": shift.employee_id.name,
                    "hours": round(total_hours, 2),
                    "cells": cells,
                }
            )
        return {
            "planning_id": self.id,
            "name": self.display_name,
            "published_on": fields.Datetime.to_string(self.published_on)
            if self.published_on
            else False,
            "days": days,
            "templates": [
                {
                    "id": template.id,
                    "name": template.name,
                    "code": self._grid_template_code(template),
                    "color": template.color or 0,
                    "hours": self._grid_template_hours(template),
                }
                for template in templates
            ],
            "groups": sorted(groups.values(), key=lambda g: g["name"]),
            "day_counts": day_counts,
            "gaps": self._grid_gaps(),
        }

    def grid_write(self, line_id, template_id):
        """Assign a template to a day line (or clear it with a falsy
        template_id). Returns a fresh grid_data()."""
        self.ensure_one()
        line = self._grid_check_line(line_id)
        template = self.env["hr.shift.template"].browse(template_id or [])
        if template_id and not template.exists():
            raise UserError(self.env._("This shift template doesn't exist anymore."))
        previous = line.template_id
        if previous != template:
            line.template_id = template
            self._grid_log_change(line, previous, template)
        return self.grid_data()

    def grid_swap(self, line_id, other_line_id):
        """Exchange the templates of two day lines. When the target line
        has no template this is simply a move. Returns a fresh grid_data()."""
        self.ensure_one()
        line = self._grid_check_line(line_id)
        other = self._grid_check_line(other_line_id)
        if line == other or (not line.template_id and not other.template_id):
            return self.grid_data()
        line_template, other_template = line.template_id, other.template_id
        line.template_id = other_template
        other.template_id = line_template
        self._grid_log_change(line, line_template, other_template)
        self._grid_log_change(other, other_template, line_template)
        return self.grid_data()

    def _grid_check_line(self, line_id):
        line = self.env["hr.shift.planning.line"].browse(line_id)
        if not line.exists() or line.planning_id != self:
            raise UserError(
                self.env._("This shift line doesn't belong to this planning.")
            )
        if line.state in ("holiday", "on_leave"):
            raise UserError(
                self.env._(
                    "%(employee)s is on leave on %(day)s: this shift can't be changed.",
                    employee=line.employee_id.name,
                    day=self._grid_day_label(line),
                )
            )
        return line

    def _grid_day_label(self, line):
        day_date = self.start_date + timedelta(days=int(line.day_number))
        return format_date(self.env, day_date, date_format="EEEE d MMM")

    def _grid_template_code(self, template):
        return template.name.split()[0] if template.name else ""

    def _grid_template_hours(self, template):
        times = template._prepare_time()
        return (
            f"{times['start_time']['hour']:02d}:{times['start_time']['minute']:02d}"
            f" – "
            f"{times['end_time']['hour']:02d}:{times['end_time']['minute']:02d}"
        )

    def _grid_gaps(self):
        """Missing employees per day, when hr_shift_coverage is installed."""
        self.ensure_one()
        gaps = {}
        if hasattr(self, "_update_coverage_gaps"):
            self._update_coverage_gaps()
            for gap in self.coverage_gap_ids:
                gaps[gap.day_number] = gaps.get(gap.day_number, 0) + gap.missing
        return gaps

    def _grid_log_change(self, line, previous, new):
        """Trace grid changes in the chatter once the week has been sent to
        the employees (the chatter comes with hr_shift_snapshot)."""
        if not self.published_on or not hasattr(self, "message_post"):
            return
        day_off = self.env._("Day off")
        self.message_post(
            body=self.env._(
                "Grid change after publication: %(employee)s — %(day)s: "
                "%(before)s → %(after)s",
                employee=line.employee_id.name,
                day=self._grid_day_label(line),
                before=previous.display_name if previous else day_off,
                after=new.display_name if new else day_off,
            )
        )
