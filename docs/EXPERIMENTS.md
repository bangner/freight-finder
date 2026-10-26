# Experiments

Both ran on a LaunchDarkly trial account with synthetic visitors. In the assistant experiment, every model call, response time and token count is real.

## 1. Does the hours-of-service panel lift bookings?

| | |
| --- | --- |
| Hypothesis | Showing US enterprise dispatchers their drivers' hours of service increases load bookings |
| Flag | `driver-hours-of-service`, rule "Enterprise in US": `off` (control) against `us` |
| Randomized by | `organization`, so everyone at one shipper sees the same thing |
| Metric | Book a load clicked: the share of organizations that book at least once |
| Size | 2,500 organizations. About 880 per variation detects 8% → 12% at 95% confidence and 80% power |

**Result** (frequentist, significance level 0.05). The simulator converts 8% of `off` and 12% of `us` visitors on purpose, so this proves the experiment pipeline works, not that the panel lifts real bookings.

- Simulator run: bookings rose from 8.1% to 11.9% (+46% relative), p = 0.002.
- LaunchDarkly, over 3,001 organizations (the 2,500 plus earlier test runs): `us` +42.2% (95% interval +11.1% to +73.4%), "significant in the desired direction".

![LaunchDarkly's results: us 42.2% above off on bookings](images/ld-hos-experiment.png)

**Decision:** for the demo, serve `us` on the rule and stop the experiment. With a real customer, rerun it on real traffic for at least a week, with a guardrail metric such as error rate, before deciding.

## 2. Assistant: concise or friendly?

| | |
| --- | --- |
| Hypothesis | If self-serve dispatchers get `friendly` instead of `concise`, answers take longer, because a larger model writing a fuller answer does more work |
| AI Config | `dispatcher-assistant`, default rule: every organization that is not enterprise |
| Variations | `concise` (control): Claude Haiku, two sentences. `friendly`: Claude Sonnet, explains and suggests a next step |
| Randomized by | `user` |
| Metrics | Response time (primary) and output tokens, both lower is better, from events the AI SDK already sends |
| Size | 500 dispatchers, one real question each (`scripts/simulate_assistant.py`) |

**Result:**

| Variation | Answers | Mean response time | Mean output tokens | Cost per answer |
| --- | --- | --- | --- | --- |
| `concise` | 262 | 1.8 s | 250 | $0.0002 |
| `friendly` | 238 | 4.0 s | 421 | $0.0049 |

- LaunchDarkly: `friendly` is 118.5% slower (95% interval +103.9% to +133.1%) and writes 68.5% more output tokens (+54.3% to +82.6%).
- No answer failed. Cost per answer is from the AI Config's Monitoring tab.
- The variations differ in model and prompt together, and neither metric measures answer quality.

![LaunchDarkly's results: friendly slower and longer on both metrics](images/ld-ai-experiment.png)

**Decision:** keep `concise` for self-serve customers and `friendly` for enterprise, where a fuller answer is worth more than twice the wait. The experiment is stopped, serving `concise`. Next: rerun on real traffic with thumbs-up rate as a metric.
