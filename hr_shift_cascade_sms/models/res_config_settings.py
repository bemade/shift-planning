# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hr_shift_cascade_sms_gateway_url = fields.Char(
        string="SMS Gateway URL",
        config_parameter="hr_shift_cascade_sms.gateway_url",
        help="URL template with {to} and {message} placeholders, e.g. "
        "https://provider.example.com/send?dst={to}&text={message}",
    )
    hr_shift_cascade_sms_gateway_method = fields.Selection(
        selection=[("GET", "GET"), ("POST", "POST")],
        string="SMS Gateway Method",
        default="GET",
        config_parameter="hr_shift_cascade_sms.gateway_method",
    )
    hr_shift_cascade_sms_enabled_by_default = fields.Boolean(
        string="Enable SMS on New Cascades",
        config_parameter="hr_shift_cascade_sms.enabled_by_default",
    )
