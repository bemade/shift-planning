# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Employees Shifts Interactive Grid",
    "summary": "Interactive weekly grid to assign, move and swap shifts",
    "version": "19.0.1.0.0",
    "author": "Bemade, Odoo Community Association (OCA)",
    "maintainers": ["XtremXpert"],
    "license": "AGPL-3",
    "website": "https://github.com/OCA/shift-planning",
    "category": "Human Resources/Shifts",
    "depends": [
        "web",
        "hr_shift",
        "hr_shift_publish",
    ],
    "data": [
        "views/shift_planning_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_shift_grid/static/src/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
}
