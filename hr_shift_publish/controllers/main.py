# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import http
from odoo.http import request


class ShiftScheduleController(http.Controller):
    @http.route(
        "/shift_schedule/<string:token>",
        type="http",
        auth="public",
        methods=["GET"],
    )
    def schedule_page(self, token):
        values = request.env["hr.shift.planning.shift"]._schedule_page_values(token)
        return request.render("hr_shift_publish.schedule_page", values)
