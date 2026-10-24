# LaunchDarkly setup

Everything the app expects to find in LaunchDarkly, in the order you need it. Steps 1 to 4 cover Part 1, step 5 covers Part 2, and steps 6 to 8 are the extra credit. Use the **Test** environment throughout.

LaunchDarkly's UI changes over time. If a label here does not match what you see, the linked LaunchDarkly doc for that step has the current wording.

## 1. Project and SDK key

1. Create a project named **ABC Freight** with key `abc-freight`. If you use another key, set `LD_PROJECT_KEY` to match.
2. Open the project's **Test** environment and copy its **SDK key** (it starts with `sdk-`). Put it in `.env` as `LAUNCHDARKLY_SDK_KEY`.

Use the SDK key, not the client-side ID or the mobile key. The app rejects keys that do not start with `sdk-`.

## 2. Part 1 flag: `eta-predictions`

| Field | Value |
| --- | --- |
| Name | ETA predictions |
| Key | `eta-predictions` (must match `ETA_FLAG` in `app/flags.py`) |
| Type | Boolean |
| Variations | `true` (Available), `false` (Unavailable) |
| Default when on | `true` |
| Default when off | `false` |

Leave the flag **Off** in Test. Turning it on is the release.

## 3. Context kind: `organization`

The app evaluates every flag with a multi-context: a `user` and an `organization`. LaunchDarkly creates the `organization` kind the first time the app sends one. To use it as the experiment's randomization unit (step 6), open **Contexts**, click the gear icon, edit `organization`, and check **Available for experiments and guarded rollouts**. If the kind is not listed yet, run the app and switch visitors once, or create it there with **Add kind** and key `organization`.

## 4. Remediation trigger

A flag trigger is a secret URL that performs one action on one flag.

1. Open `eta-predictions`, then the Test environment's overflow menu, then **Configuration in environment**.
2. Under **Triggers**, click **+ Add trigger**.
3. **Trigger type**: Generic trigger. **Action**: turn the flag off.
4. Click **Save trigger** and copy the URL right away; LaunchDarkly shows it only once.
5. Put it in `.env` as `LD_TRIGGER_URL`.

Triggers are only available on some LaunchDarkly plans. If you cannot add one, use the REST fallback instead: create an access token with a **Writer** role under **Account settings > Authorization**, and set `LD_API_TOKEN`, `LD_PROJECT_KEY=abc-freight` and `LD_ENV_KEY=test`. `scripts/rollback.sh` uses whichever is configured.

Reference: [Flag triggers](https://launchdarkly.com/docs/home/releases/triggers), [Update feature flag (semantic patch)](https://launchdarkly.com/docs/api/feature-flags/patch-feature-flag).

## 5. Part 2 flag: `driver-hours-of-service`

| Field | Value |
| --- | --- |
| Name | Driver hours of service |
| Key | `driver-hours-of-service` (must match `HOS_FLAG` in `app/flags.py`) |
| Type | String |
| Variations | `off`, `us`, `canada` (values exactly as written) |
| Default rule | `off` |
| Off variation | `off` |

Turn the flag **On** with the default rule serving `off`. Nobody sees the panel yet. Then build the targeting while a browser is open, so the audience sees each step land:

1. **Individual target.** Add a target for the **organization** context kind: key `lakeshore-logistics` gets `us`. Riley's view changes; nobody else's does.
2. **Rule 1, "Enterprise in Canada".** If `organization` `plan` is one of `enterprise` AND `organization` `region` is one of `CA`, serve `canada`.
3. **Rule 2, "Enterprise in US".** If `organization` `plan` is one of `enterprise` AND `organization` `region` is one of `US`, serve `us`.

Expected results are in the visitor table in the README. To check why a visitor got a value, open **Contexts**, find the organization, and look at its flag evaluations.

## 6. Experiment: does the HOS panel lift bookings?

**Metric.** Create a metric:

| Field | Value |
| --- | --- |
| Name | Book a load clicked |
| Event key | `book-load-clicked` (sent by `POST /api/track` and by the simulator) |
| Measurement | Custom conversion binary: did the context convert at least once |
| Success | Higher is better |

**Experiment.**

1. **Create > Experiment**. Name: "HOS panel and bookings". Hypothesis: "Showing US enterprise dispatchers their drivers' hours of service increases load bookings."
2. **Assignment method**: LaunchDarkly flag or config, flag `driver-hours-of-service`.
3. **Targeting rule**: Enterprise in US.
4. **Randomize by**: `organization` (it must match the context kind the rule targets).
5. **Variation split**: `off` 50%, `us` 50%, `canada` 0%. Control: `off`.
6. **Metric**: Book a load clicked, set as primary.
7. Save, then **Start**.

Then send traffic: `python scripts/simulate_traffic.py --visitors 500`. Each run creates new synthetic US enterprise organizations. The default made-up conversion rates are 8% for `off` and 12% for `us`. Results appear on the experiment's results tab within a few minutes. The traffic is synthetic: it proves the wiring, not the business result.

Reference: [Creating experiments](https://launchdarkly.com/docs/home/experimentation/create).

## 7. AI Config: `dispatcher-assistant`

In the left sidebar the area may be called **AI Configs** or **Agents > Configs**. Create a **Completion** config:

| Field | Value |
| --- | --- |
| Key | `dispatcher-assistant` (must match `ASSISTANT_CONFIG` in `app/flags.py`) |

Add two variations. The `{{ shipper_name }}` and `{{ loads }}` variables are filled in by the app from the visitor's data.

| Variation | Model | Model parameter | System message |
| --- | --- | --- | --- |
| `concise` | A fast Anthropic model, for example Claude Haiku | `max_tokens` = 300 | You are the dispatcher assistant for {{ shipper_name }}. Answer in at most two sentences, using only these loads:<br>{{ loads }} |
| `friendly` | A larger Anthropic model, for example Claude Sonnet | `max_tokens` = 500 | You are a friendly dispatcher assistant for {{ shipper_name }}. Explain your answer briefly and suggest a next step. Use only these loads:<br>{{ loads }} |

**Targeting**: default rule serves `concise`. Add a rule: `organization` `plan` is one of `enterprise` serves `friendly`.

Set `MODEL_API_KEY` in `.env` to an Anthropic API key and restart the app. The assistant panel appears for every visitor whose config is enabled. Usage, latency, tokens and thumbs up/down show on the config's **Monitoring** tab.

Optional: run an experiment on the AI Config with thumbs-up rate as the metric, the same way as step 6.

Reference: [AI Configs quickstart](https://launchdarkly.com/docs/home/ai-configs/quickstart).

## 8. Slack integration

1. Install the LaunchDarkly app in your Slack workspace and run `/launchdarkly account` to connect it.
2. In a channel such as `#abc-freight-releases`, subscribe to the Test environment's flag changes:
   ```text
   /launchdarkly subscribe -p abc-freight -e test
   ```
3. Run `scripts/rollback.sh`. The channel shows that the trigger turned `eta-predictions` off.

The Slack app is not available on LaunchDarkly's EU or federal instances; use Slack incoming webhooks there.

Reference: [Slack app](https://launchdarkly.com/docs/integrations/slack).
