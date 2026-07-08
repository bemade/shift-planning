When a shift must be filled at short notice — an employee calls in sick
at 5 AM — the coordinator's job is a cascade of phone calls. This
module turns that cascade into a managed process on top of *Employees
Shifts Coverage* and *Employees Shifts Requests*:

- From any coverage gap, launch a **replacement cascade**: the module
  builds the ordered list of who to call.
- Candidates are filtered on hard criteria (free that day, matching job
  position and department, matching declared availabilities) and
  ordered by **fewest assigned hours in the week** (overtime control),
  then **least recently offered** (fairness rotation).
- The coordinator can reorder the list before starting — the human
  override required for automated decisions affecting employees.
- Each contact outcome is logged (accepts / declines / no answer).
  An acceptance creates and approves an open shift claim, assigns the
  shift line and recomputes the coverage gaps; when every candidate is
  exhausted the cascade escalates loudly instead of failing silently.

This is the manual-channel foundation: SMS and voice (IVR) channels
plug on top of the same cascade and candidate models.
