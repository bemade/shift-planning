# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Employees Shifts Split Replacement",
    "summary": "Replace one employee by two: split a shift into two parts",
    "version": "19.0.1.0.0",
    "author": "Bemade, Odoo Community Association (OCA)",
    "maintainers": ["XtremXpert"],
    "license": "AGPL-3",
    "website": "https://github.com/OCA/shift-planning",
    "category": "Human Resources/Shifts",
    "depends": ["hr_shift_coverage"],
    "data": [
        "security/ir.model.access.csv",
        "wizards/hr_shift_split_wizard_views.xml",
        "views/hr_shift_coverage_gap_views.xml",
    ],
}
