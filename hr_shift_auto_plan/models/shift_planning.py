# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models

# Continuity preference stops adding days to an employee's week once they
# reach this many assigned days, so one person does not absorb a full
# 7-day week just because they were picked first on Monday.
MAX_CONTINUITY_DAYS = 5


class ShiftPlanning(models.Model):
    _inherit = "hr.shift.planning"

    def _auto_plan_pick(self, cascade):
        """Pick the candidate for one slot, preferring weekly continuity.

        Order of preference:
        1. Candidates already assigned to the same template this week
           (most days first), while they stay under MAX_CONTINUITY_DAYS —
           schedule stability matters in residential care, for the
           employees and the residents alike;
        2. Otherwise the cascade order (fewest hours, then fairness
           rotation), skipping employees already at MAX_CONTINUITY_DAYS
           when someone lighter is available.
        """
        candidates = cascade.candidate_ids.filtered(
            lambda candidate: candidate.state == "pending"
        )
        if not candidates:
            return candidates
        assigned_lines = self.shift_ids.line_ids.filtered(
            lambda line: line.state == "assigned"
        )
        scored = []
        for sequence, candidate in enumerate(candidates):
            employee_lines = assigned_lines.filtered(
                lambda line, candidate=candidate: line.employee_id
                == candidate.employee_id
            )
            same_template = len(
                employee_lines.filtered(
                    lambda line, cascade=cascade: line.template_id
                    == cascade.template_id
                )
            )
            total_days = len(employee_lines)
            scored.append((candidate, same_template, total_days, sequence))
        under_cap = [entry for entry in scored if entry[2] < MAX_CONTINUITY_DAYS]
        pool = under_cap or scored
        continuity = [entry for entry in pool if entry[1] > 0]
        if continuity:
            continuity.sort(key=lambda entry: (-entry[1], entry[3]))
            return continuity[0][0]
        pool.sort(key=lambda entry: entry[3])
        return pool[0][0]

    def _auto_plan_set_weekly_templates(self):
        """Give fully uniform weeks their weekly template so the
        assignment kanban groups them in the right column. Writing the
        same template on a uniform shift is a no-op on its lines."""
        for shift in self.shift_ids.filtered(lambda s: not s.template_id):
            templates = shift.line_ids.mapped("template_id")
            unassigned = shift.line_ids.filtered(lambda line: not line.template_id)
            if len(templates) == 1 and not unassigned:
                shift.template_id = templates

    def action_auto_plan(self):
        """Fill every coverage gap with the best available candidate.

        Each assignment goes through a replacement cascade and an
        approved claim, so the audit trail is identical to a manual
        cascade — only the consent step is skipped, which is the
        purpose of auto-planning.
        """
        self.ensure_one()
        self._update_coverage_gaps()
        filled = unfilled = 0
        # Iterate on a snapshot: gaps are recomputed after each fill
        gaps = [
            {
                "template_id": gap.template_id.id,
                "day_number": gap.day_number,
                "rule_id": gap.rule_id.id,
                "missing": gap.missing,
            }
            for gap in self.coverage_gap_ids
        ]
        # Group the week's slots by template so continuity picks chain up
        gaps.sort(key=lambda gap: (gap["template_id"], gap["day_number"]))
        for gap in gaps:
            for _index in range(gap["missing"]):
                cascade = self.env["hr.shift.cascade"].create(
                    {
                        "planning_id": self.id,
                        "template_id": gap["template_id"],
                        "day_number": gap["day_number"],
                        "rule_id": gap["rule_id"],
                    }
                )
                cascade.action_generate_candidates()
                candidate = self._auto_plan_pick(cascade)
                if not candidate:
                    cascade.action_cancel()
                    unfilled += 1
                    continue
                cascade.state = "running"
                candidate.action_accept()
                filled += 1
        self._update_coverage_gaps()
        self._auto_plan_set_weekly_templates()
        message = self.env._(
            "Auto-plan: %(filled)s shift(s) assigned, %(unfilled)s slot(s) "
            "left unfilled (no eligible candidate).",
            filled=filled,
            unfilled=unfilled,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if not unfilled else "warning",
                "title": self.env._("Auto-plan finished"),
                "message": message,
                "sticky": bool(unfilled),
            },
        }
