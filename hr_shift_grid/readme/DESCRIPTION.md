This module adds an interactive weekly grid to the shift planning stack,
similar to commercial scheduling tools: one row per employee (grouped by
department), one column per day of the week ordered following the user's
language settings, and one colored chip per assigned day shift.

From the grid the coordinator can:

- assign a shift template to an empty day with two clicks;
- change or remove an assigned shift from a small contextual menu;
- move a shift to another day or employee with drag & drop;
- swap two shifts by dropping one chip onto another;
- watch the weekly hours per employee and the assignments per day being
  recalculated live;
- see the coverage gaps of each day (when the Shift Coverage module is
  installed) refreshed after every change.

When the week has already been sent to the employees, the first change asks
for a confirmation and every subsequent change is logged in the chatter of
the planning (when the chatter is available on the planning).

At installation, shift templates without a color receive one automatically
from their start hour: green for morning shifts, orange for
afternoon/evening shifts and purple for night shifts.
