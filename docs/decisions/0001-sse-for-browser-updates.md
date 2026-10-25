# 1. Server-Sent Events for browser updates

**Status:** accepted

## Context

An open page must change within about a second of a flag change, with no reload and no polling. Updates only flow from server to browser.

## Decision

Use Server-Sent Events: `GET /events` with `StreamingResponse`, and `EventSource` in the browser.

## Consequences

- One-way is all we need, and `EventSource` reconnects by itself. The server sends a full snapshot on every connect, so a reconnect never misses a change.
- It is plain HTTP, so it passes through proxies that allow long responses, with no extra dependency.
- Rejected: WebSockets (two-way, more moving parts, nothing to send upstream); polling (either slow or wasteful, when the change should feel instant); LaunchDarkly's client-side JavaScript SDK. The assignment allows any of LaunchDarkly's five most common SDKs, JavaScript included. We chose the server-side Python SDK so flag decisions, targeting data and feature data stay on the server, and the browser only renders what it is sent.
