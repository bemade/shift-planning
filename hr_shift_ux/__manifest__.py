# Copyright 2026 Bemade Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Employees Shifts UX",
    "summary": "Coordinator-friendly views for the shift planning stack",
    "version": "19.0.1.0.0",
    "author": "Bemade, Odoo Community Association (OCA)",
    "maintainers": ["XtremXpert"],
    "license": "AGPL-3",
    "website": "https://github.com/OCA/shift-planning",
    "category": "Human Resources/Shifts",
    "depends": [
        "hr_shift_auto_plan",
        "hr_shift_cascade",
        "hr_shift_coverage",
        "hr_shift_publish",
        "hr_shift_request",
        "hr_shift_rotation",
        "hr_shift_snapshot",
        "hr_shift_split",
        "hr_shift_timeline",
        "hr_shift_workload",
    ],
    "data": [
        "views/shift_planning_views.xml",
        "views/shift_planning_shift_views.xml",
        "views/hr_shift_coverage_gap_views.xml",
        "views/menu.xml",
    ],
}
