# 3. Flag trigger for remediation, REST API as fallback, no admin endpoint

**Status:** accepted

## Context

Part 1 needs a way to turn a bad feature off quickly, from a script or a monitoring tool, without two sources of truth.

## Decision

Primary: the LaunchDarkly dashboard. Scripted: a LaunchDarkly flag trigger (a secret URL whose only action is "turn the flag off"), called by `scripts/rollback.sh`. Fallback for any flag or for plans without triggers: the REST API's `turnFlagOff` semantic patch with an access token.

## Consequences

- LaunchDarkly stays the only source of truth; the app never overrides a flag locally.
- The trigger URL can only turn one flag off, so leaking it is far less harmful than leaking an API token. It is still treated as a secret and can be reset.
- Repeating the call is harmless.
- Rejected: a `POST /admin/feature-flag` endpoint in the app. It would need its own authentication and would hold an API token in the web process, for no gain over the trigger.
