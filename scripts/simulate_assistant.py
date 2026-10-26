"""Ask the dispatcher assistant real questions as synthetic dispatchers, for the AI Config experiment.

    python scripts/simulate_assistant.py --users 500

Each synthetic dispatcher works for a new self-serve shipper (pro plan), so the
AI Config's default rule, where the experiment runs, decides their variation.
Each one asks a single question through app.assistant.ask, the same code the
page uses, so LaunchDarkly receives the real duration, token and success events
for every answer.

The dispatchers are synthetic; the model calls and the measurements are real.
This needs MODEL_API_KEY and costs money: about half a cent per friendly answer
and a fiftieth of a cent per concise one, so 500 dispatchers cost under $2.
"""

import argparse
import logging
import secrets
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ldclient  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from app import assistant  # noqa: E402
from app.contexts import Visitor, build_context  # noqa: E402
from app.flags import sdk_config  # noqa: E402
from app.loads import loads_for  # noqa: E402
from app.settings import ConfigError, Settings, load_settings  # noqa: E402

# Questions a dispatcher might ask about today's loads.
QUESTIONS = [
    "Which loads are at risk today?",
    "Which load is running latest, and why?",
    "Which drivers should I check in with first?",
    "Is anything still waiting at pickup?",
    "Summarize today's loads in one line each.",
    "Has anything already been delivered?",
    "Which receiver should I call about a late arrival?",
    "What is the earliest arrival still to come?",
]


def synthetic_visitor(i: int, run: str) -> Visitor:
    """A dispatcher at a new self-serve shipper: not enterprise, so the AI Config's default rule applies."""
    return Visitor(
        key=f"sim-{run}-{i}",
        name=f"Simulated dispatcher {i}",
        email="",
        role="dispatcher",
        anonymous=False,
        org_key=f"sim-{run}-org-{i}",
        org_name=f"Simulated shipper {i}",
        plan="pro",
        region="US" if i % 2 == 0 else "CA",
        fleet_size=20 + i % 60,
        beta_tester=False,
    )


def simulate(users: int, settings: Settings, run: str) -> tuple[dict[str, list[dict]], int]:
    """Returns ({model: [usage of each answer]}, number of runs that failed)."""
    results: dict[str, list[dict]] = defaultdict(list)
    errors = 0
    for i in range(users):
        visitor = synthetic_visitor(i, run)
        question = QUESTIONS[i % len(QUESTIONS)]
        try:
            answer = assistant.ask(visitor, build_context(visitor), loads_for(visitor), question, settings)
            results[answer["model"]].append(answer["usage"])
        except assistant.AssistantUnavailable:
            raise  # the AI Config is off for these dispatchers: nothing to measure
        except Exception:
            errors += 1  # assistant.ask has already reported it to LaunchDarkly as an error
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{users} asked", flush=True)
    return dict(results), errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users", type=int, default=60)
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
    except ConfigError as error:
        sys.exit(f"Configuration error: {error}")
    if assistant.is_dry_run(settings):
        sys.exit("Set MODEL_API_KEY and leave ASSISTANT_DRY_RUN off: a dry run calls no model, so nothing is measured.")

    ldclient.set_config(sdk_config(settings.sdk_key, "abc-freight-assistant-simulator"))
    client = ldclient.get()
    if not client.is_initialized():
        sys.exit("Could not reach LaunchDarkly. Check the SDK key and your network.")

    run = secrets.token_hex(3)  # new context keys each run, so each run adds new dispatchers
    print(f"Run {run}: {args.users} synthetic dispatchers, one question each")
    try:
        results, errors = simulate(args.users, settings, run)
    except assistant.AssistantUnavailable as error:
        sys.exit(f"{error} Check that dispatcher-assistant is on in LaunchDarkly.")
    finally:
        client.close()  # flushes every exposure and metric event

    for model, usages in sorted(results.items()):
        seconds = [usage["duration_ms"] / 1000 for usage in usages]
        tokens = [usage["output_tokens"] for usage in usages]
        print(
            f"  {model:<20} {len(usages):3d} answers, median {statistics.median(seconds):.1f} s, "
            f"mean {statistics.mean(tokens):,.0f} output tokens"
        )
    print(f"  errors: {errors}")
    print("Results appear on the experiment in LaunchDarkly within a few minutes.")


if __name__ == "__main__":
    main()
