# ABC Freight: feature flags for a shipper portal

A shipper portal that uses LaunchDarkly to test features in production, release them instantly and roll them back in a second. Python (FastAPI), the LaunchDarkly server-side SDK, Server-Sent Events and plain JavaScript.

![The Live ETA panel after release](docs/images/2-eta-on.png)

## What the brief asks, and where it is

| Part | What it shows | LaunchDarkly features | Where |
| --- | --- | --- | --- |
| 1. Release and remediate | Live ETA panel: tested by ABC Freight's own staff, released to everyone, rolled back by a trigger. The page never reloads. | Boolean flag, individual target, change listener, trigger | `app/flags.py`, `app/main.py`, `scripts/rollback.sh` |
| 2. Target | Hours-of-service panel: one shipper by name, enterprise shippers by region | Multi-context, individual and rule-based targeting | `app/contexts.py` |
| Extra: Experimentation | Does the panel lift bookings? +42% on synthetic traffic (simulator set to 8% → 12%) | Metric, experiment | [Experiments](docs/EXPERIMENTS.md) |
| Extra: AI Configs | The assistant's model and prompt change with no deploy; an experiment picks the variation | AI Config, AI metrics, feedback | `app/assistant.py` |
| Extra: Integrations | Flag changes post to Slack; LaunchDarkly shows where each flag is used; pull requests get a comment listing the flags they touch | Slack app, code references, PR flag comments | [Setup](docs/SETUP.md#8-slack), [Slack messages](docs/images/ld-slack.png), [example PR comment](https://github.com/bangner/freight-finder/pull/6) |
| Extra: Configuration as code | The LaunchDarkly setup is Terraform; `terraform plan` shows the live project matches | Terraform provider | `terraform/` |

## Quickstart

Needs Python 3.11+, a LaunchDarkly account (a [trial](https://launchdarkly.com/start-trial/) works), and Terraform 1.7+ for the quick setup. Written for macOS and Linux; on Windows use WSL.

```bash
git clone https://github.com/bangner/freight-finder.git && cd freight-finder
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

1. Set up LaunchDarkly with Terraform or by hand: [docs/SETUP.md](docs/SETUP.md).
2. Put the SDK key and the trigger URL in `.env`.
3. Run `python -m app` and open http://127.0.0.1:8000.

Docker instead: `docker build -t abc-freight . && docker run --rm -p 8000:8000 --env-file .env abc-freight`

| Variable | For | Required |
| --- | --- | --- |
| `LAUNCHDARKLY_SDK_KEY` | Everything. Server-side key for the Test environment, starts with `sdk-` | Yes |
| `LD_TRIGGER_URL` | `scripts/rollback.sh` | For Part 1 |
| `LD_API_TOKEN`, `LD_PROJECT_KEY`, `LD_ENV_KEY` | Rollback through the REST API instead | No |
| `MODEL_API_KEY` | Real assistant answers (Anthropic). Without it, a free dry run | No |
| `ASSISTANT_DRY_RUN` | `true` keeps the dry run even with a key | No |

No key or token ever reaches the browser.

## Demo

Keep one tab open: nothing below reloads the page. The footer shows each flag's value and LaunchDarkly's reason, such as `TARGET_MATCH`. `python scripts/explain.py` prints the same for every visitor.

**Part 1: release and remediate**

1. Start with `eta-predictions` off and its default rule serving `false`.
2. Turn the flag on. Guest sees nothing; Quinn, ABC Freight's own QA engineer, sees the ETA panel.
3. As Quinn, click **Refresh predictions**: it times out. The bug is found before any customer sees it.
4. Release anyway: set the default rule to `true`. Every page shows the panel within a second.
5. Roll back with `scripts/rollback.sh`. The trigger turns the flag off, every page drops the panel, and Slack posts the change.

**Part 2: targeting.** Switch **Viewing as**:

| Visitor | Organization (plan, region) | Hours-of-service panel | Reason |
| --- | --- | --- | --- |
| Dana | Prairie Haul (enterprise, CA) | Canadian rules | Rule 2, Enterprise in Canada |
| Sam | Lone Star Freight (enterprise, US) | US rules, or none while the experiment runs | Rule 1, Enterprise in US |
| Riley | Lakeshore Logistics (pro, US) | US rules | Individual target |
| Alex, Quinn, Guest | Free, internal, anonymous | None | No match |

Turning the flag off hides every panel: the kill switch beats targeting.

**Experimentation.** `python scripts/simulate_traffic.py --visitors 2500 --seed 2026` sends synthetic shippers through the experiment. Results: [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).

**AI Configs.** Ask "Which loads arrive today?", switch the variation in LaunchDarkly, and ask again: the model, prompt and tone change with no restart. Enterprise shippers (Sam, Dana) get `friendly`; everyone else gets `concise`.

| Before the release | The bug, found by an internal tester |
| --- | --- |
| ![Loads table only](docs/images/1-original.png) | ![Refresh predictions times out](docs/images/3-eta-error.png) |
| **Dana: Canadian rules** | **The assistant (test stub answer)** |
| ![Hours-of-service panel with Canadian rules](docs/images/4-hos-canada.png) | ![Dispatcher assistant panel](docs/images/5-assistant.png) |

## Tests

```bash
pip install -r requirements-dev.txt
pytest                                                    # no LaunchDarkly account needed
python -m playwright install chromium && pytest tests/e2e # real browser
cd terraform && terraform init -backend=false && terraform test
```

- 66 Python tests and 5 Terraform tests. They use the SDK's `TestData` source and a mocked Terraform provider: no keys, no network.
- The browser test flips flags under an open page and checks it never reloads.
- CI runs everything on every push, plus a secret scan and a Docker build.

## Repository

| Path | Contents |
| --- | --- |
| `app/` | FastAPI app: flags and listeners (`flags.py`), contexts, the two features, the assistant |
| `static/` | HTML, CSS and JavaScript, no framework |
| `scripts/` | Rollback, the two simulators, `explain.py` |
| `terraform/` | The LaunchDarkly setup as code |
| `tests/` | Unit, integration and browser tests |
| `docs/` | [Setup](docs/SETUP.md), [Architecture](docs/ARCHITECTURE.md), [Runbook](docs/RUNBOOK.md), [Experiments](docs/EXPERIMENTS.md) |

## Limitations

- One process, with SSE connections in memory. [Architecture](docs/ARCHITECTURE.md) covers scaling.
- Preset visitors, no login. Guests share one anonymous key; production would give each its own.
- Fictional data. The hours-of-service figures are simplified and not for compliance.
- Anthropic models only.

MIT license.
