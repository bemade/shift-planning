1. Go to *Settings > Employees > Shift Cascade SMS*.
2. Set the SMS gateway URL template, with `{to}` and `{message}`
   placeholders for GET gateways, e.g.
   `https://provider.example.com/send?dst={to}&text={message}`.
   For POST gateways, set the method to POST: the number and message
   are sent as `to` and `message` form fields.
3. Optionally enable *Enable by Default* so every new cascade sends
   SMS offers.
4. Make sure employees have a mobile (or work) phone number and that
   `web.base.url` points to a URL reachable from their phones.
