# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Employees Shifts Replacement Cascade - SMS",
    "summary": "Send cascade offers by SMS with tokenized accept links",
    "version": "19.0.1.0.0",
    "author": "Bemade, Odoo Community Association (OCA)",
    "maintainers": ["XtremXpert"],
    "license": "AGPL-3",
    "website": "https://github.com/OCA/shift-planning",
    "category": "Human Resources/Shifts",
    "depends": ["hr_shift_cascade"],
    "data": [
        "data/ir_cron.xml",
        "views/templates.xml",
        "views/hr_shift_cascade_views.xml",
        "views/res_config_settings_views.xml",
    ],
}
