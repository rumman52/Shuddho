# Phase 11 Transaction Chaos Qualification

## Invariant

No consequential action occurs twice.

## Transaction failure outcomes

| Failure | Expected outcome |
| --- | --- |
| provider timeout | preserve uncertainty and require reconciliation |
| lost provider response | do not automatically retry mutation |
| duplicate message | reuse existing execution identity |
| duplicate execution binding | reject second binding |
| expired approval | fail closed |
| provider failure after mutation boundary | reconcile from evidence |

## Release gate

- One transaction execution binding maximum
- Reconciliation evidence preserved
- Duplicate consequential actions prevented
- Expired approvals cannot execute
