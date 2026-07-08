# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import http
from odoo.http import request


class ShiftCascadeController(http.Controller):
    @http.route(
        "/shift_cascade/<string:token>",
        type="http",
        auth="public",
        methods=["GET"],
    )
    def cascade_offer(self, token):
        values = request.env["hr.shift.cascade.candidate"]._token_action(token)
        return request.render("hr_shift_cascade_sms.offer_page", values)

    @http.route(
        "/shift_cascade/<string:token>/<string:answer>",
        type="http",
        auth="public",
        methods=["POST"],
        # The unguessable per-candidate token is the capability: the
        # answer must work from an SMS link without any session.
        csrf=False,
    )
    def cascade_answer(self, token, answer):
        if answer not in ("accept", "decline"):
            answer = None
        values = request.env["hr.shift.cascade.candidate"]._token_action(
            token, action=answer
        )
        return request.render("hr_shift_cascade_sms.offer_page", values)
