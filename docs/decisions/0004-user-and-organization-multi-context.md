# 4. Evaluate with a user + organization multi-context

**Status:** accepted

## Context

ABC Freight sells to companies. Rollouts are decided per customer (plan, region, beta program), while the person using the page still matters for analytics and the assistant.

## Decision

Every evaluation uses a multi-context: `user` (key, name, role, private email) and `organization` (key, name, plan, region, fleet size, beta tester). Rules and individual targets use the organization.

## Consequences

- One rule reaches every dispatcher at an enterprise customer at once, which is how B2B releases work.
- Experiments randomize by organization, so everyone at one shipper sees the same variation.
- Email is marked private, so it is used for evaluation but not stored in LaunchDarkly.
- The `organization` context kind must be enabled for experiments in LaunchDarkly (setup step 3).
