# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)


class HrShiftSmsGateway(models.AbstractModel):
    """Provider-agnostic HTTP SMS gateway.

    The gateway is configured with system parameters so any HTTP SMS
    provider (e.g. the SIP trunk provider's SMS API) can be plugged
    without code:

    - ``hr_shift_cascade_sms.gateway_url``: URL template with ``{to}``
      and ``{message}`` placeholders (already URL-encoded values).
    - ``hr_shift_cascade_sms.gateway_method``: ``GET`` (default) or
      ``POST`` (placeholders are then sent as form data ``to`` and
      ``message`` and must not appear in the URL).
    """

    _name = "hr.shift.sms.gateway"
    _description = "Shift Cascade SMS Gateway"

    @api.model
    def send(self, number, message):
        """Send an SMS. Returns True on success, False otherwise.

        Never raises: a delivery failure must not break the cascade —
        the caller logs the outcome and the cron retries or escalates.
        """
        params = self.env["ir.config_parameter"].sudo()
        url_template = params.get_param("hr_shift_cascade_sms.gateway_url")
        if not url_template:
            _logger.warning(
                "SMS gateway not configured "
                "(hr_shift_cascade_sms.gateway_url): SMS to %s not sent.",
                number,
            )
            return False
        method = (
            params.get_param("hr_shift_cascade_sms.gateway_method") or "GET"
        ).upper()
        try:
            if method == "POST":
                response = requests.post(
                    url_template,
                    data={"to": number, "message": message},
                    timeout=10,
                )
            else:
                response = requests.get(
                    url_template.format(
                        to=requests.utils.quote(number or ""),
                        message=requests.utils.quote(message or ""),
                    ),
                    timeout=10,
                )
            response.raise_for_status()
        except requests.RequestException:
            _logger.exception("SMS delivery to %s failed.", number)
            return False
        return True
