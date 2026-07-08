# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Employees Shifts Coverage",
    "summary": "Define minimum staffing per shift and detect coverage gaps",
    "version": "19.0.1.0.0",
    "author": "Bemade, Odoo Community Association (OCA)",
    "maintainers": ["XtremXpert"],
    "license": "AGPL-3",
    "website": "https://github.com/OCA/shift-planning",
    "category": "Human Resources/Shifts",
    "depends": ["hr_shift"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_shift_coverage_rule_views.xml",
        "views/hr_shift_coverage_gap_views.xml",
        "views/shift_planning_views.xml",
    ],
}
