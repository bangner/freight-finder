"""Runtime configuration, read once from environment variables.

Copy .env.example to .env and fill in real values. Nothing in this module
is ever sent to the browser.
"""

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing."""


@dataclass(frozen=True)
class Settings:
    # Server-side SDK key for the LaunchDarkly environment (Test, for the demo).
    # Find it under Project settings > Environments > Test > SDK key.
    sdk_key: str
    # Optional: API key for the dispatcher assistant's model provider. When unset,
    # the assistant runs as a dry run: it shows what LaunchDarkly serves and calls no model.
    model_api_key: str | None
    # Optional: ASSISTANT_DRY_RUN=true keeps the dry run even with a key set,
    # for example to rehearse a demo at no cost.
    assistant_dry_run: bool = False


def load_settings() -> Settings:
    sdk_key = os.environ.get("LAUNCHDARKLY_SDK_KEY", "").strip()
    if not sdk_key:
        raise ConfigError(
            "LAUNCHDARKLY_SDK_KEY is not set. Copy .env.example to .env and add the "
            "server-side SDK key from your LaunchDarkly Test environment."
        )
    if not sdk_key.startswith("sdk-"):
        raise ConfigError(
            "LAUNCHDARKLY_SDK_KEY does not look like a server-side SDK key (it should "
            "start with 'sdk-'). Client-side IDs and mobile keys will not work here."
        )
    model_api_key = os.environ.get("MODEL_API_KEY", "").strip() or None
    dry_run = os.environ.get("ASSISTANT_DRY_RUN", "").strip().lower() in {"1", "true", "yes"}
    return Settings(sdk_key=sdk_key, model_api_key=model_api_key, assistant_dry_run=dry_run)
