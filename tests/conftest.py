"""Shared fixtures. Tests use the SDK's TestData source, so they need no network and no keys."""

import ldclient
import pytest
from fastapi.testclient import TestClient
from ldclient import Config
from ldclient.integrations.test_data import TestData
from ldclient.interfaces import UpdateProcessor

from app.flags import ASSISTANT_CONFIG, ETA_FLAG, HOS_FLAG
from app.main import create_app
from app.settings import Settings

FAKE_SDK_KEY = "sdk-00000000-test-not-a-real-key"
FAKE_MODEL_KEY = "model-key-test-not-real"

HOS_OFF, HOS_US, HOS_CANADA = 0, 1, 2


class _StopOnce(UpdateProcessor):
    """ldclient.set_config() closes the previous client again; TestData only tolerates one stop."""

    def __init__(self, inner):
        self._inner = inner
        self._stopped = False

    def start(self):
        self._inner.start()

    def initialized(self):
        return self._inner.initialized()

    def stop(self):
        if not self._stopped:
            self._stopped = True
            self._inner.stop()


def ld_test_config(td: TestData) -> Config:
    """An SDK Config whose flag data comes from TestData.

    TestData normally writes straight into the SDK's store, which skips the
    flag-change notifications the real streaming connection produces. Routing
    it through config.data_source_update_sink (the same path the streaming
    data source uses) makes flag_tracker listeners fire, so the SSE bridge is
    tested the way it runs in production.
    """

    def data_source(config, store, ready):
        return _StopOnce(td(config, config.data_source_update_sink or store, ready))

    return Config(FAKE_SDK_KEY, update_processor_class=data_source, send_events=False)


INTERNAL_ORG = "abc-freight"


def eta(td: TestData, on: bool, *, internal_only: bool = False) -> None:
    """The ETA flag. internal_only: on, but served only to ABC Freight's own organization (the staged release)."""
    flag = td.flag(ETA_FLAG).boolean_flag()
    if internal_only:
        flag = flag.on(True).fallthrough_variation(False).variation_for_key("organization", INTERNAL_ORG, True)
    else:
        flag = flag.variation_for_all(on)
    td.update(flag)


def hos(td: TestData, *, on: bool = True, targets: bool = False, rules: bool = False) -> None:
    """The hours-of-service flag as terraform/flags.tf and docs/LAUNCHDARKLY_SETUP.md describe it."""
    flag = td.flag(HOS_FLAG).variations("off", "us", "canada").off_variation(HOS_OFF)
    flag = flag.fallthrough_variation(HOS_OFF).on(on)
    if targets:
        flag = flag.variation_for_key("organization", "lakeshore-logistics", HOS_US)
    if rules:
        (
            flag.if_match_context("organization", "plan", "enterprise")
            .and_match_context("organization", "region", "US")
            .then_return(HOS_US)
        )
        (
            flag.if_match_context("organization", "plan", "enterprise")
            .and_match_context("organization", "region", "CA")
            .then_return(HOS_CANADA)
        )
    td.update(flag)


ASSISTANT_VALUE = {
    "_ldMeta": {"enabled": True, "variationKey": "concise", "version": 1},
    "model": {"name": "claude-haiku-5-5", "parameters": {"max_tokens": 300}},
    "provider": {"name": "anthropic"},
    "messages": [
        {"role": "system", "content": "You are the dispatcher assistant for {{shipper_name}}.\n{{loads}}"},
    ],
}


def assistant_config(td: TestData, enabled: bool, **parameters) -> None:
    """The AI Config, enabled or not. Keyword arguments add model parameters, e.g. effort="low"."""
    model = ASSISTANT_VALUE["model"]
    value = {
        **ASSISTANT_VALUE,
        "_ldMeta": {**ASSISTANT_VALUE["_ldMeta"], "enabled": enabled},
        "model": {**model, "parameters": {**model["parameters"], **parameters}},
    }
    td.update(td.flag(ASSISTANT_CONFIG).value_for_all(value))


@pytest.fixture
def td():
    return TestData.data_source()


@pytest.fixture
def ld(td):
    """A live SDK client (ldclient.get()) backed by TestData."""
    ldclient.set_config(ld_test_config(td))
    yield td
    ldclient.get().close()


def make_client(td: TestData, model_api_key: str | None = None, assistant_dry_run: bool = False) -> TestClient:
    settings = Settings(sdk_key=FAKE_SDK_KEY, model_api_key=model_api_key, assistant_dry_run=assistant_dry_run)
    return TestClient(create_app(ld_test_config(td), settings))


@pytest.fixture
def client(td):
    with make_client(td) as c:
        yield c


@pytest.fixture
def client_with_model(td):
    with make_client(td, FAKE_MODEL_KEY) as c:
        yield c
