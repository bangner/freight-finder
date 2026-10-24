"""Send synthetic visitors through the hours-of-service experiment.

    python scripts/simulate_traffic.py --visitors 500

Each synthetic visitor is a new US enterprise shipper, so it lands in the
experiment's audience. The script evaluates driver-hours-of-service (which
records the exposure) and then, with a made-up probability that depends on
the variation, sends the book-load-clicked conversion event.

The traffic and the rates are synthetic. They prove the wiring end to end;
they say nothing about real shippers.
"""

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ldclient  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from ldclient import Config, Context, LDClient  # noqa: E402

from app.flags import HOS_FLAG  # noqa: E402
from app.settings import ConfigError, load_settings  # noqa: E402

EVENT = "book-load-clicked"


def synthetic_context(i: int, run: str) -> Context:
    user = Context.builder(f"sim-{run}-user-{i}").kind("user").name(f"Simulated dispatcher {i}").build()
    org = (
        Context.builder(f"sim-{run}-org-{i}")
        .kind("organization")
        .name(f"Simulated shipper {i}")
        .set("plan", "enterprise")
        .set("region", "US")
        .set("fleet_size", 50 + i % 250)
        .set("beta_tester", False)
        .build()
    )
    return Context.create_multi(user, org)


def simulate(client: LDClient, visitors: int, rates: dict[str, float], rng: random.Random, run: str) -> dict:
    """Returns {variation: [exposures, conversions]}."""
    exposures: Counter[str] = Counter()
    conversions: Counter[str] = Counter()
    for i in range(visitors):
        context = synthetic_context(i, run)
        value = client.variation(HOS_FLAG, context, "off")
        exposures[value] += 1
        if rng.random() < rates.get(value, 0.0):
            client.track(EVENT, context)
            conversions[value] += 1
    return {value: [exposures[value], conversions[value]] for value in exposures}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--visitors", type=int, default=500)
    parser.add_argument("--rate-off", type=float, default=0.08, help="conversion rate when the panel is off")
    parser.add_argument("--rate-us", type=float, default=0.12, help="conversion rate when the US panel is shown")
    parser.add_argument("--seed", type=int, default=None, help="fix the random sequence for a repeatable run")
    args = parser.parse_args()

    load_dotenv()
    try:
        settings = load_settings()
    except ConfigError as error:
        sys.exit(f"Configuration error: {error}")

    ldclient.set_config(Config(settings.sdk_key))
    client = ldclient.get()
    if not client.is_initialized():
        sys.exit("Could not reach LaunchDarkly. Check the SDK key and your network.")

    rng = random.Random(args.seed)
    run = f"{rng.randrange(16**6):06x}"  # new context keys each run, so each run adds new visitors
    results = simulate(client, args.visitors, {"off": args.rate_off, "us": args.rate_us}, rng, run)
    client.close()  # flushes every exposure and conversion event

    print(f"Run {run}: sent {args.visitors} synthetic visitors")
    for value, (seen, converted) in sorted(results.items()):
        print(f"  {value:>7}: {seen:4d} exposures, {converted:4d} conversions ({converted / seen:.1%})")
    print("Results appear on the experiment in LaunchDarkly within a few minutes.")


if __name__ == "__main__":
    main()
