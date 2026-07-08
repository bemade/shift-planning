This module automates the *Employees Shifts Replacement Cascade* over
SMS:

- When a cascade starts, the first N candidates (configurable blast
  size) receive an SMS with the shift and a tokenized link.
- The link opens a minimal mobile page — no login, no app — with two
  buttons: **I take it** / **Not available**. The first candidate to
  accept gets the shift (through the open shift claim mechanics);
  late acceptances get a friendly "already filled" page.
- Unanswered offers expire after a configurable delay and the next
  candidates are contacted automatically (cron, every 2 minutes).
- The SMS gateway is a provider-agnostic HTTP template configured in
  Employees settings, so any HTTP SMS API (e.g. your SIP trunk
  provider's) works without code. A delivery failure never breaks the
  cascade: it is logged on the candidate and the cron moves on.

The SMS content is minimal by design — shift, day and week only, never
any beneficiary-related information.
