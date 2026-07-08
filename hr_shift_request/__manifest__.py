# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Employees Shifts Requests",
    "summary": "Employee availabilities, open shift claims and shift swaps",
    "version": "19.0.1.0.0",
    "author": "Bemade, Odoo Community Association (OCA)",
    "maintainers": ["XtremXpert"],
    "license": "AGPL-3",
    "website": "https://github.com/OCA/shift-planning",
    "category": "Human Resources/Shifts",
    "depends": ["hr_shift_coverage"],
    "data": [
        "security/hr_shift_request_security.xml",
        "security/ir.model.access.csv",
        "views/hr_shift_availability_views.xml",
        "views/hr_shift_claim_views.xml",
        "views/hr_shift_swap_views.xml",
        "views/hr_shift_coverage_gap_views.xml",
    ],
}
