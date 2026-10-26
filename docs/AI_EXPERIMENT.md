# Experiment: concise or friendly assistant?

The optional AI Configs experiment, run on a LaunchDarkly trial account. The dispatchers asking questions are synthetic. Every model call, response time and token count is real.

## Design

| | |
| --- | --- |
| Question | Is the friendly variation's longer answer worth its extra time and cost for self-serve customers? |
| Hypothesis | The concise variation answers faster and with fewer output tokens than the friendly one, so it should stay the default for self-serve customers. |
| AI Config | `dispatcher-assistant`, on its default rule: every organization that isn't enterprise. Enterprise customers keep `friendly` through their own rule. |
| Variations | Control `concise`: Claude Haiku, answering in at most two sentences. Treatment `friendly`: Claude Sonnet, explaining briefly and suggesting a next step. |
| Randomization unit | `user` |
| Primary metric | Assistant response time: the average of `$ld:ai:duration:total` per user, in milliseconds. Lower is better. |
| Secondary metric | Assistant output tokens: the average of `$ld:ai:tokens:output` per user. Lower is better. |

Both metrics come from events the AI SDK already sends for every answer (`app/assistant.py`), so the experiment needed no new instrumentation. Users who were assigned a variation but asked nothing are left out of both averages.

## Run

```bash
python scripts/simulate_assistant.py --users 60
```

60 synthetic self-serve dispatchers each asked one of eight dispatcher questions through `app.assistant.ask`, the same code the page uses. LaunchDarkly assigned each one a variation.

| Variation | Answers | Median response time | Mean output tokens |
| --- | --- | --- | --- |
| `concise` (Claude Haiku) | 35 | 1.7 s | 230 |
| `friendly` (Claude Sonnet) | 25 | 3.9 s | 447 |

- No answer failed. The split is 35 to 25 because LaunchDarkly assigns each user at random; it evens out with more traffic.
- `friendly` took about 2.3 times as long and produced about 1.9 times as many output tokens.
- At list prices, Sonnet's output costs 20 times Haiku's per token ($10 against $0.50 per million), so a friendly answer's output costs roughly 40 times a concise one's. The whole run cost well under a dollar.

LaunchDarkly's results tab compares the variations with its own statistics. It averages per user, so its figures are means rather than the medians above.

## Decision

Keep `concise` as the default for self-serve customers. Keep `friendly` for enterprise customers, where a longer answer with a suggested next step is worth about twice the wait and many times the cost. To apply it in LaunchDarkly, stop the experiment and serve `concise` on the default rule.

What this run does not measure is whether dispatchers find the friendly answers more helpful; that needs real users. The next step is the same experiment on real traffic, with thumbs-up rate (`$ld:ai:feedback:user:positive`, already sent by the app) as a third metric.
