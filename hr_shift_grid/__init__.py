from . import models


def post_init_hook(env):
    """Give the shift templates a sensible default color so the grid is
    readable out of the box: green for morning shifts, orange for
    afternoon/evening shifts, purple for night shifts."""
    templates = (
        env["hr.shift.template"]
        .with_context(active_test=False)
        .search([("color", "=", 0)])
    )
    for template in templates:
        if template.start_time < 6 or template.start_time >= 22:
            template.color = 5
        elif template.start_time < 12:
            template.color = 10  # green
        elif template.start_time < 18:
            template.color = 2  # orange
        else:
            template.color = 5  # purple
