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
        1. Candidates whose week stays within their contract hours after
           taking this shift — overtime should never come from the
           automatic planner. Overloading is only a last resort;
        2. Among them, candidates already assigned to the same template
           this week (most days first), while they stay under
           MAX_CONTINUITY_DAYS — schedule stability matters in
           residential care, for the employees and the residents alike;
        3. Otherwise the cascade order (fewest hours, then fairness
           rotation), skipping employees already at MAX_CONTINUITY_DAYS
           when someone lighter is available.

        Returns a (candidate, overloaded) tuple; ``candidate`` is empty
        when nobody is eligible.
        """
        candidates = cascade.candidate_ids.filtered(
            lambda candidate: candidate.state == "pending"
        )
        if not candidates:
            return candidates, False
        assigned_lines = self.shift_ids.line_ids.filtered(
            lambda line: line.state == "assigned"
        )
        duration = cascade.template_id.end_time - cascade.template_id.start_time
        if duration <= 0:
            duration += 24
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
            shift = candidate.line_id.shift_id
            fits_hours = (
                not shift.allocated_hours
                or shift.planned_hours + duration <= shift.allocated_hours + 1e-6
            )
            scored.append((candidate, same_template, total_days, sequence, fits_hours))
        within_hours = [entry for entry in scored if entry[4]]
        base_pool = within_hours or scored
        under_cap = [entry for entry in base_pool if entry[2] < MAX_CONTINUITY_DAYS]
        pool = under_cap or base_pool
        continuity = [entry for entry in pool if entry[1] > 0]
        if continuity:
            continuity.sort(key=lambda entry: (-entry[1], entry[3]))
            chosen = continuity[0]
        else:
            pool.sort(key=lambda entry: entry[3])
            chosen = pool[0]
        return chosen[0], not chosen[4]

    def _auto_plan_scarcity(self, rule_id, template_id):
        """How many employees could ever take this slot: job and
        department of the rule, and a matching availability (employees
        without any declaration are available for everything)."""
        rule = self.env["hr.shift.coverage.rule"].browse(rule_id)
        template = self.env["hr.shift.template"].browse(template_id)
        employees = self.env["hr.employee"].search([("shift_planning", "=", True)])
        if rule.job_id:
            employees = employees.filtered(lambda e: e.job_id == rule.job_id)
        if rule.department_id:
            employees = employees.filtered(
                lambda e: e.department_id == rule.department_id
            )
        count = 0
        for employee in employees:
            availabilities = self.env["hr.shift.availability"].search(
                [("employee_id", "=", employee.id)]
            )
            if not availabilities or any(
                availabilities._matches(template, day) for day in map(str, range(7))
            ):
                count += 1
        return count

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
        filled = unfilled = overloaded = 0
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
        # Fill the scarcest slots first (fewest eligible employees, e.g.
        # nights restricted by availabilities) while everyone is still
        # light, then group by template so continuity picks chain up.
        scarcity = {
            (gap["rule_id"], gap["template_id"]): self._auto_plan_scarcity(
                gap["rule_id"], gap["template_id"]
            )
            for gap in gaps
        }
        gaps.sort(
            key=lambda gap: (
                scarcity[(gap["rule_id"], gap["template_id"])],
                gap["template_id"],
                gap["day_number"],
            )
        )
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
                candidate, over_hours = self._auto_plan_pick(cascade)
                if not candidate:
                    cascade.action_cancel()
                    unfilled += 1
                    continue
                if over_hours:
                    overloaded += 1
                    cascade.message_post(
                        body=self.env._(
                            "Assigned to %(employee)s beyond their contract "
                            "hours: no lighter candidate was available.",
                            employee=candidate.employee_id.display_name,
                        )
                    )
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
        if overloaded:
            message += self.env._(
                " %(overloaded)s assignment(s) exceed contract hours — "
                "no lighter candidate was available; see the cascades.",
                overloaded=overloaded,
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if not (unfilled or overloaded) else "warning",
                "title": self.env._("Auto-plan finished"),
                "message": message,
                "sticky": bool(unfilled or overloaded),
            },
        }
