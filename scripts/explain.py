"""Show what LaunchDarkly serves each preset visitor, and why.

    python scripts/explain.py

For every visitor in the page's "Viewing as" menu, prints each flag's value
and the evaluation reason LaunchDarkly gives for it (OFF, FALLTHROUGH,
TARGET_MATCH, RULE_MATCH, ...), plus the AI Config variation and model the
assistant would use. Run it after each step of docs/SETUP.md to
check the setup, or when a visitor sees something you did not expect.
ERROR (FLAG_NOT_FOUND) means the key in LaunchDarkly does not match app/flags.py.

It sends no events to LaunchDarkly, so it never counts as an experiment exposure.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ldclient  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from ldclient import LDClient  # noqa: E402

from app.contexts import VISITORS, build_context  # noqa: E402
from app.flags import ASSISTANT_CONFIG, FLAG_FALLBACKS, describe_reason, sdk_config  # noqa: E402
from app.settings import ConfigError, load_settings  # noqa: E402


def describe_config(value: object) -> str:
    """An AI Config's value is the whole config; show only its variation and model."""
    if not isinstance(value, dict):
        return "missing"
    meta = value.get("_ldMeta") or {}
    if not meta.get("enabled"):
        return "disabled"
    model = (value.get("model") or {}).get("name") or "no model"
    return f"{meta.get('variationKey') or '?'} ({model})"


def explain(client: LDClient) -> list[tuple[str, str, str, str]]:
    """One row per visitor and key: (visitor, key, value, reason)."""
    rows = []
    for visitor in VISITORS.values():
        context = build_context(visitor)
        for key, fallback in FLAG_FALLBACKS.items():
            detail = client.variation_detail(key, context, fallback)
            rows.append((visitor.key, key, json.dumps(detail.value), describe_reason(detail.reason)))
        detail = client.variation_detail(ASSISTANT_CONFIG, context, None)
        rows.append((visitor.key, ASSISTANT_CONFIG, describe_config(detail.value), describe_reason(detail.reason)))
    return rows


def main() -> None:
    load_dotenv()
    try:
        settings = load_settings()
    except ConfigError as error:
        sys.exit(f"Configuration error: {error}")

    # send_events=False: looking at flags must not count as an exposure or a conversion.
    ldclient.set_config(sdk_config(settings.sdk_key, "abc-freight-explain", send_events=False))
    client = ldclient.get()
    if not client.is_initialized():
        sys.exit("Could not reach LaunchDarkly. Check the SDK key and your network.")

    current = None
    for visitor_key, key, value, reason in explain(client):
        if visitor_key != current:
            visitor = VISITORS[visitor_key]
            print(f"\n{visitor.name}, {visitor.org_name} ({visitor.plan}, {visitor.region})")
            current = visitor_key
        print(f"  {key:<25} {value:<30} {reason}")
    client.close()


if __name__ == "__main__":
    main()
