# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models


class ShiftPlanning(models.Model):
    _inherit = "hr.shift.planning"

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
                candidate = cascade.candidate_ids[:1]
                if not candidate:
                    cascade.action_cancel()
                    unfilled += 1
                    continue
                cascade.state = "running"
                candidate.action_accept()
                filled += 1
        self._update_coverage_gaps()
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
