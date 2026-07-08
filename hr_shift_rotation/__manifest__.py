# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Employees Shifts Rotations",
    "summary": "Rotating week patterns applied over multiple plannings",
    "version": "19.0.1.0.0",
    "author": "Bemade, Odoo Community Association (OCA)",
    "maintainers": ["XtremXpert"],
    "license": "AGPL-3",
    "website": "https://github.com/OCA/shift-planning",
    "category": "Human Resources/Shifts",
    "depends": ["hr_shift"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_shift_rotation_views.xml",
        "wizards/hr_shift_rotation_apply_views.xml",
    ],
}
