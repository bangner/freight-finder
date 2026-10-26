import pytest

from app.contexts import VISITORS
from app.features import _shift, eta_predictions
from app.loads import loads_for


@pytest.mark.parametrize("visitor", ["sam", "dana"])  # one US and one Canadian shipper
def test_predicted_arrival_is_scheduled_arrival_plus_delay(visitor):
    loads = loads_for(VISITORS[visitor])
    for load, prediction in zip(loads, eta_predictions(loads), strict=True):
        if load.status == "Delivered":
            assert prediction["predicted_arrival"] == "Delivered"
            assert prediction["delay_minutes"] == 0
        else:
            assert prediction["predicted_arrival"] == _shift(load.scheduled_arrival, prediction["delay_minutes"])


def test_us_predictions_are_unchanged():
    predictions = eta_predictions(loads_for(VISITORS["sam"]))
    assert [p["predicted_arrival"] for p in predictions] == [
        "Today 16:52",
        "Today 19:10",
        "Tomorrow 10:40",
        "Tomorrow 06:50",
        "Delivered",
    ]


def test_shift_handles_early_late_and_midnight():
    assert _shift("Today 17:40", 22) == "Today 18:02"
    assert _shift("Today 20:05", -5) == "Today 20:00"
    assert _shift("Today 23:50", 20) == "Tomorrow 00:10"
