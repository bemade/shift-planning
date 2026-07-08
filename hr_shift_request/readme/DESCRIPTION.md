This module adds the employee-facing interaction layer on top of
*Employees Shifts* (`hr_shift`) and *Employees Shifts Coverage*
(`hr_shift_coverage`):

- **Availabilities**: employees declare the shifts and week days they
  are available for, giving managers a candidate list when filling
  open shifts.
- **Open shift claims**: employees claim a slot straight from the
  coverage gaps of a planning; a shift manager approves, and the shift
  line is assigned automatically.
- **Shift swaps**: an employee offers one of their shifts to a
  colleague — as a hand-over or in exchange for one of the colleague's
  shifts. The colleague accepts, a shift manager approves, and the
  shift lines are updated automatically.

All requests carry a chatter thread, so every hand-over is notified
and auditable.
