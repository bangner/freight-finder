# Setup

The complete first run, from a fresh clone to a working demo.

- **Required** for the two homework parts (release and remediate, targeting): sections 1 to 4. Stop at [the checkpoint](#4-start-the-app-and-check-it) once the app works.
- **Optional:** the dispatcher assistant, the two experiments, Slack and the GitHub integrations, in [section 5](#5-optional-extras). Each stands on its own.

Run every command from the repository root (`freight-finder/`) with the virtual environment active, unless a step says otherwise. There are two `.env` files:

- **The app's `.env`** in the repository root: the SDK key, the trigger URL and the optional keys.
- **`terraform/.env`**: only the access token Terraform uses. Never put it in the app's `.env`.

## 1. Prerequisites

- Python 3.11+.
- A LaunchDarkly account. A [trial](https://launchdarkly.com/start-trial/) works.
- For the Terraform route: Terraform 1.7+ and a LaunchDarkly access token with the **Admin** role (**Account settings > Authorization**). The Writer role cannot create context kinds.
- macOS or Linux. On Windows, use WSL.

## 2. Prepare the checkout

```bash
git clone https://github.com/bangner/freight-finder.git && cd freight-finder
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

This creates the app's `.env`. The next section fills in `LAUNCHDARKLY_SDK_KEY` and `LD_TRIGGER_URL`. Everything else in it is optional; see the [reference](#6-reference).

## 3. Configure LaunchDarkly

Everything happens in the **Test** environment. Pick one route; both end at the same checkpoint in section 4.

- **[Route A, Terraform](#route-a-terraform):** a few commands.
- **[Route B, by hand](#route-b-by-hand):** the same settings, step by step in the LaunchDarkly UI.

### Route A: Terraform

From the repository root:

```bash
cd terraform
cp .env.example .env                # terraform/.env: add the Admin token here
set -a && . ./.env && set +a
terraform init && terraform apply
terraform output -raw sdk_key       # paste into the app's .env (../.env) as LAUNCHDARKLY_SDK_KEY
terraform output -raw trigger_url   # paste into the app's .env (../.env) as LD_TRIGGER_URL
cd ..                               # back to the repository root
```

**Creates:** project `abc-freight` (Test and Production), context kind `organization`, both flags with their starting targeting, the trigger, the AI Config `dispatcher-assistant` with both variations, and its two metrics. The assistant and the experiments still need a few clicks, covered in [section 5](#5-optional-extras); the required demo does not.

**Good to know:**

- No flag triggers on your plan? Apply with `-var create_trigger=false` and use the [REST fallback](#rollback-without-a-trigger).
- Terraform owns the definitions: variations, metrics, models and prompts. It creates the targeting once and then leaves it to LaunchDarkly, so an apply never undoes a release, a rollback or an experiment.
- `terraform plan` reporting "No changes" means every field Terraform manages matches the code. Targeting is handed to the UI, so the plan does not check it.
- The state file holds the SDK key and trigger URL in plain text. It is git-ignored; a team would use an encrypted remote backend.
- Already set up by hand? `terraform/imports.tf.example` adopts the existing project.
- The project is protected from `terraform destroy`. To remove a trial, delete the project in LaunchDarkly.

Next: [section 4](#4-start-the-app-and-check-it).

### Route B: By hand

#### Project and SDK key

- Create project **ABC Freight**, key `abc-freight`.
- Copy the Test environment's **SDK key** (starts with `sdk-`) into the app's `.env` as `LAUNCHDARKLY_SDK_KEY`. Not the client-side ID or mobile key.

#### Start the app once

LaunchDarkly creates the `organization` context kind the first time it sees one, and the next step targets an organization. So start the app now, in a second terminal from the repository root:

```bash
source .venv/bin/activate
python -m app
```

Open http://127.0.0.1:8000 and pick **Quinn** under **Viewing as**. The page shows only the loads table: the flags do not exist yet, so every panel stays hidden. Leave the app running; it picks up each change below with no restart.

#### Flag `eta-predictions` (Part 1)

| Field | Value |
| --- | --- |
| Key | `eta-predictions` (must match `app/flags.py`) |
| Type | Boolean: `true`, `false` |
| Default rule | `false`. The form preselects `true`; change it |
| Off variation | `false` |
| Temporary | Yes, a release flag |

- Leave it **Off**.
- **+** > **Target individuals**: context kind `organization`, key `abc-freight`, serve `true`.

![eta-predictions before a release: off, organization abc-freight targeted with true, default rule false](images/ld-eta-targeting.png)

#### Trigger

- `eta-predictions` > Test > **Configuration in environment** > **Triggers** > **+ Add trigger**.
- Generic trigger, action: turn the flag off.
- Copy the URL (shown once) into the app's `.env` as `LD_TRIGGER_URL`. Treat it like a password.

<a id="rollback-without-a-trigger"></a>**No triggers on your plan?** Create an access token with the Writer role and set `LD_API_TOKEN` in the app's `.env`. `scripts/rollback.sh` then turns the flag off through the REST API.

#### Flag `driver-hours-of-service` (Part 2)

| Field | Value |
| --- | --- |
| Key | `driver-hours-of-service` (must match `app/flags.py`) |
| Type | String: `off`, `us`, `canada` |
| Default rule and off variation | `off` |
| Temporary | No |

Turn it **On**, then add:

1. **Target individuals**: `organization` `lakeshore-logistics` → `us`.
2. Rule 1, "Enterprise in US": `organization` `plan` is one of `enterprise` AND `region` is one of `US` → `us`.
3. Rule 2, "Enterprise in Canada": the same with `CA` → `canada`.

Next: section 4, with the app still running.

## 4. Start the app and check it

If the app is not already running from Route B, start it from the repository root, with the virtual environment active:

```bash
python -m app
```

Open http://127.0.0.1:8000. Docker instead: `docker build -t abc-freight . && docker run --rm -p 8000:8000 --env-file .env abc-freight`

Check:

- http://127.0.0.1:8000/healthz shows `"launchdarkly_initialized": true`.
- In another terminal, `python scripts/explain.py` prints every visitor's value and reason, with no events sent:
  - `eta-predictions` is `false` with reason `OFF` for everyone.
  - `driver-hours-of-service` matches the visitor table in the [README](../README.md#demo): Dana `canada`, Sam and Riley `us`, the rest `off`.
  - The assistant shows `missing` or `disabled` until you set it up in section 5. Its panel stays hidden.
- On the page, Dana, Sam and Riley see the hours-of-service panel; nobody sees the ETA panel.

Before each demo: `eta-predictions` **Off**, default rule `false`.

**Required setup is complete.** The [demo in the README](../README.md#demo) works from here. Everything below is optional.

## 5. Optional extras

### Dispatcher assistant (AI Config)

**Terraform route:** the config and both variations exist. Skip to **Targeting**.

**By hand:**

- **AI Configs** (or **Agents > Configs**) > completion config, key `dispatcher-assistant`, provider Anthropic.
- Two variations. Set `max_tokens` under **Add parameters > Model parameters**:

| Variation | Model | `max_tokens` |
| --- | --- | --- |
| `concise` | `claude-haiku-5-5` | 2000 |
| `friendly` | `claude-sonnet-5-5` | 4000 |

System message for `concise`:

```text
You are the dispatcher assistant for {{ shipper_name }}. Answer in at most two sentences, using only these loads:
{{ loads }}

Reply in plain text, without Markdown.
```

System message for `friendly`:

```text
You are a friendly dispatcher assistant for {{ shipper_name }}. Explain your answer briefly and suggest a next step. Use only these loads:
{{ loads }}

Reply in plain text, without Markdown.
```

- Type the line breaks with Enter, not `<br>`. The app fills in `{{ shipper_name }}` and `{{ loads }}`.
- Thinking counts toward `max_tokens`: with 300–500, answers get cut off.
- Optional: custom parameter `{"effort": "low"}` (`low` to `max`) for faster, cheaper answers.

**Targeting (both routes):** `dispatcher-assistant` > **Targeting** (Test): turn it on, default rule `concise`, and a custom rule `organization` · `plan` (not `key`) · is one of `enterprise` → `friendly`.

**Answers:** without `MODEL_API_KEY`, the assistant runs a free dry run that shows the model and prompt LaunchDarkly served. Set `MODEL_API_KEY` in the app's `.env` and restart for real answers.

**Check:** the assistant panel appears; `python scripts/explain.py` shows `friendly` for Sam and Dana and `concise` for everyone else.

![The Monitoring tab: cost, satisfaction and requests for each variation](images/ld-ai-monitoring.png)

### Experiment: HOS panel and bookings

Synthetic traffic, free. Results: [EXPERIMENTS.md](EXPERIMENTS.md).

1. **Context kind:** **Contexts** > gear icon > `organization` > tick **Available for experiments and guarded rollouts**. Terraform cannot change this setting.
2. **Metric** "Book a load clicked":
   - Terraform route: from `terraform/`, with `terraform/.env` loaded as in Route A, run `terraform apply -var create_booking_metric=true`, then `cd ..`.
   - By hand: event `book-load-clicked`, occurrence (conversion), higher is better, unit `organization`.
3. **Experiment:**
   - Flag `driver-hours-of-service`, rule Enterprise in US, randomize by `organization`.
   - Split: `off` 50% (control), `us` 50%, `canada` 0%. The metric above is primary.
   - Hypothesis: "Showing US enterprise dispatchers their drivers' hours of service increases load bookings." Replace all of LaunchDarkly's "If… then… because…" template.
4. **Traffic:** `python scripts/simulate_traffic.py --visitors 2500 --seed 2026`

**Check:** the experiment's results page counts exposures for both variations. While it runs, Sam may see no panel (`RULE_MATCH (rule 1, in experiment)`): Lone Star Freight is in the control group.

### Experiment: concise or friendly?

Real model calls, under $2 for 500 users. Needs the [assistant](#dispatcher-assistant-ai-config) with `MODEL_API_KEY` set and `ASSISTANT_DRY_RUN` off. Results: [EXPERIMENTS.md](EXPERIMENTS.md).

1. **Metrics.** The Terraform route creates both. By hand, both are: value, averaged per user, units without events excluded, **lower is better**.
   - Assistant response time: `$ld:ai:duration:total`, ms.
   - Assistant output tokens: `$ld:ai:tokens:output`, tokens.
2. **Experiment:**
   - On the default rule, randomized by `user`: `concise` 50% (control), `friendly` 50%. Response time is primary.
   - Hypothesis: "If self-serve dispatchers get the friendly variation instead of the concise one, then answers take longer, because a larger model writing a fuller answer does more work."
3. **Traffic:** `python scripts/simulate_assistant.py --users 500`

**Check:** the script prints a summary per variation, and the experiment's results page fills in. Afterwards, stop the experiment and serve `concise`.

### Slack

- Install the LaunchDarkly Slack app, then run `/launchdarkly account`.
- In a channel: `/launchdarkly subscribe -p abc-freight -e test`

**Check:** every change posts, including the trigger's rollback and Terraform's changes (comment "Terraform").

![Slack messages from LaunchDarkly: two changes made by Terraform, and an experiment's winning variation](images/ld-slack.png)

### Code references and pull request comments

- Create an access token with the Writer role and store it as a repository secret: `gh secret set LD_ACCESS_TOKEN --repo <your-account>/freight-finder`
- `.github/workflows/code-references.yml` then sends each flag's usages to LaunchDarkly on every push to `main`.
- `.github/workflows/flag-pull-requests.yml` comments on each pull request with the flags it touches, and links the pull request from each flag in LaunchDarkly.
- `.launchdarkly/coderefs.yaml` adds aliases, so references through `ETA_FLAG` and `HOS_FLAG` count too.
- Without the secret, both workflows skip.

**Check:** after the next push to `main`, each flag's **Code references** tab lists its files.

## 6. Reference

### The app's `.env`

| Variable | For | Required | Where to get it |
| --- | --- | --- | --- |
| `LAUNCHDARKLY_SDK_KEY` | Everything | Yes | Test environment's server-side SDK key, starts with `sdk-`. Route A: `terraform output -raw sdk_key` |
| `LD_TRIGGER_URL` | `scripts/rollback.sh` | For Part 1 | The trigger on `eta-predictions`. Route A: `terraform output -raw trigger_url` |
| `LD_API_TOKEN` | Rollback through the REST API instead of the trigger | No | Access token, Writer role |
| `LD_PROJECT_KEY`, `LD_ENV_KEY` | The REST fallback | No | Defaults `abc-freight`, `test` |
| `MODEL_API_KEY` | Real assistant answers (Anthropic) | No | Anthropic console. Without it, a free dry run |
| `ASSISTANT_DRY_RUN` | `true` keeps the dry run even with a key | No | |
| `HOST`, `PORT` | Where `python -m app` listens | No | Defaults `127.0.0.1`, `8000` |

`.env.example` is the copyable template. No key or token ever reaches the browser.

### Common problems

| Symptom | Cause and fix |
| --- | --- |
| `No module named app` | Run from the repository root, with the virtual environment active. After Route A, `cd ..` out of `terraform/`. |
| `/healthz` shows `"launchdarkly_initialized": false` | Every feature is serving its fallback. Check that `LAUNCHDARKLY_SDK_KEY` is the server-side SDK key (not the client-side ID or mobile key) and that the app can reach LaunchDarkly. |
| `explain.py` shows `ERROR (FLAG_NOT_FOUND)` | The flag key in LaunchDarkly does not match `app/flags.py`. |
| Terraform fails creating the context kind | The token needs the Admin role. |
| Sam sees no hours-of-service panel | The bookings experiment is running and Lone Star Freight is in the control group. |
| `scripts/rollback.sh` cannot roll back | Set `LD_TRIGGER_URL`, or `LD_API_TOKEN` for the REST fallback. |
