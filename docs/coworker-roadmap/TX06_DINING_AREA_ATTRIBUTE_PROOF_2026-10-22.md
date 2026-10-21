# TX-06: dining-area seating attribute proof (22 October 2026)

## Root cause

When a reservation requested a specific `dining_area_id`, the OpenTable availability adapter checked the requested `reservation_attribute` only if provider `attributes` happened to be a list. Missing, null, and malformed attributes bypassed the check. Consequently the adapter could claim an explicitly selected dining area supported the reviewed seating without a matching provider signal.

## Change

Require a nonempty list of string attributes containing the immutable requested seating value for the exact matching area. Otherwise skip the candidate Standard inventory slot and return the existing definitive `reservation_not_available` when no qualifying slot remains. The booking POST still requires a fresh availability digest match; the change does not add any payment, retry, or mutation path.

## Regression scope

`tests/test_opentable_availability_types.py` covers missing, null, scalar, object, mixed, empty, and wrong seating attributes, plus an explicitly valid list. Tests simulate OpenTable locally; they never book a table.

## Gates

Run focused and required CI on the final PR SHA, obtain independent reviewer approval and enforce native `main` branch protections (V-01) before merge. No staging credentials, real provider reservations, payment handling or production activation are established by this change.
