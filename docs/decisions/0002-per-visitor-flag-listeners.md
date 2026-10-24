# 2. One flag-value-change listener per open connection

**Status:** accepted

## Context

The Python SDK reports changes through `flag_tracker`. `add_listener` fires for any change to any flag configuration, even when no visitor's value moved. `add_flag_value_change_listener(key, context, fn)` fires only when that context's value changes.

## Decision

Each SSE connection registers a value-change listener for its own visitor's context, for each watched key, and removes them in a `finally` block.

## Consequences

- Targeting changes reach only the browsers whose value changed (Part 2 needs this), with no fan-out logic of our own.
- Cost: one evaluation per connection per change. That is in-memory and cheap; at very large scale, group connections by context (see ARCHITECTURE.md).
- Listeners run on an SDK thread, so they hand off to asyncio with `call_soon_threadsafe`.
- Leaks are visible: `/healthz` reports open streams, and a test checks cleanup.
