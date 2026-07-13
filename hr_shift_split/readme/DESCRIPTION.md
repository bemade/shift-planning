When nobody can take a whole shift, replace one employee by two: this
module splits a shift into two partial shifts at a chosen cut time.

The two parts are regular shift templates linked to their parent, so
they work everywhere shifts do (assignments, workload, publication).
Coverage detection understands the split: a pair of assigned parts
counts as one employee covering the parent shift, so no false gap is
reported when both halves are staffed — and a real gap remains when
only one is.

With the replacement cascade module installed, splitting an open slot
launches one cascade per part, each with its own ordered call list.
Employees already working that day are called too (after the free
ones) when the part doesn't overlap their existing shift: accepting
gives them an extra line on top of it.
