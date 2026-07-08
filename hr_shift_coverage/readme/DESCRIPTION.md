This module extends *Employees Shifts* (`hr_shift`) with **coverage
rules**: the minimum number of employees — optionally per job position
and department — that must be assigned to each shift template, every day
the template covers.

It is designed for organizations providing continuous (24/7) services,
such as residential care facilities, where every time slot must meet a
minimum staffing grid (e.g. the night shift always requires 2 attendants
and 1 auxiliary nurse).

Checking a weekly planning produces a list of **coverage gaps**: for
each rule and each day, how many employees are required, assigned, and
missing.
