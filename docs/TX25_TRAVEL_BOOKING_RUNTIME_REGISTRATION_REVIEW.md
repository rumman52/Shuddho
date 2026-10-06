# TX-25 Travel Booking Runtime Registration Review

TX-25 is an inert review compiler after TX-22. It does not register
`travel_booking_create`, change the transaction-operation allowlist, enable a
feature flag, create an ExternalAction, collect identity documents, grant payment
authority, or call a provider.

TX-25 requires the exact fresh TX-20 registration proposal, the exact TX-22
conformance artifact, and a fresh explicit human review performed after the
conformance run.

It recomputes the TX-22 conformance digest and requires exact continuity for:

- provider and operation;
- adapter revision and travel kind;
- TX-19 qualification SHA-256;
- TX-20 registration-proposal SHA-256;
- adapter admission, preview, hosted-handoff and idempotency digests;
- the reviewed traveler-data transmission field set;
- bounded provider I/O evidence;
- all zero-authority flags.

The only successful status is:

`eligible_for_runtime_registration_review`

Even then, registration, operation allowlisting, ExternalAction exposure,
runtime enablement, identity authority and payment authority remain false. Any
actual runtime-registration change must be a later, separately reviewed code and
deployment change with its own activation verification.
