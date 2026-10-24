# 5. A three-value string flag for hours of service

**Status:** accepted

## Context

The hours-of-service panel must show different rules in the US (11 h driving in a 14 h window) and Canada (13 h in a 16 h window), or not appear at all.

## Decision

One string flag, `driver-hours-of-service`, with variations `off`, `us` and `canada`.

## Consequences

- One flag carries both "who sees it" and "which version", so targeting rules read naturally ("enterprise in CA serves canada").
- It cannot get into a contradictory state, as two boolean flags could (US on and Canada on).
- Experiments can include a subset of variations by giving `canada` 0% of the split.
- Code must treat unknown values as off; `app/main.py` only renders values it recognizes.
