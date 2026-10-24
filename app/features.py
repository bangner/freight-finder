"""The two new features. Each one is only ever called behind its flag.

Keeping the feature code here, separate from the original page data in
loads.py, means turning a flag off removes the whole feature: nothing in
this module runs and nothing it produces reaches the browser.
"""

from app.loads import Load

# --- Live ETA predictions (flag: eta-predictions) ---------------------------

# Canned model output, keyed by position in the visitor's load list.
_ETA_MODEL = [
    {
        "predicted_arrival": "Today 16:52",
        "delay_minutes": 22,
        "risk": "medium",
        "reason": "Heavy traffic on the route",
    },
    {"predicted_arrival": "Today 19:10", "delay_minutes": -5, "risk": "low", "reason": "On schedule"},
    {
        "predicted_arrival": "Tomorrow 10:40",
        "delay_minutes": 100,
        "risk": "high",
        "reason": "Late pickup; dock appointment moved",
    },
    {"predicted_arrival": "Tomorrow 06:50", "delay_minutes": 5, "risk": "low", "reason": "On schedule"},
    {"predicted_arrival": "Delivered", "delay_minutes": 0, "risk": "low", "reason": "Delivered"},
]


def eta_predictions(loads: list[Load]) -> list[dict]:
    return [{"load_id": load.id, **prediction} for load, prediction in zip(loads, _ETA_MODEL, strict=True)]


class PredictionServiceError(RuntimeError):
    """The deliberate bug used to demonstrate a problem release."""


def refresh_eta_predictions() -> None:
    # Simulated defect in the new release: the prediction service call fails.
    # This is what the Part 1 demo rolls back with the kill switch.
    raise PredictionServiceError("ETA prediction service timed out after 30 s")


# --- Driver hours of service (flag: driver-hours-of-service) ----------------

# Published limits for property-carrying drivers (simplified for display):
# US (FMCSA): 11 h driving inside a 14 h on-duty window, 30 min break after 8 h driving.
# Canada, south of 60°N: 13 h driving inside a 16 h window. No equivalent 8 h break rule.
HOS_RULES = {
    "us": {"label": "US (FMCSA)", "drive_limit": 11.0, "window": 14.0, "break_after": 8.0},
    "canada": {"label": "Canada (south of 60°N)", "drive_limit": 13.0, "window": 16.0, "break_after": None},
}

# Hours each load's driver has used today: (driving, on-duty window elapsed, driving since break).
_DRIVER_LOGS = [(6.5, 8.0, 3.0), (9.25, 11.5, 6.0), (0.0, 0.5, 0.0), (10.25, 12.5, 7.75), (4.0, 6.0, 4.0)]


def _fmt(hours: float) -> str:
    minutes = round(max(hours, 0) * 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def hours_of_service(loads: list[Load], ruleset: str) -> dict:
    """Remaining drive time per driver under the given rule set ("us" or "canada")."""
    rules = HOS_RULES[ruleset]
    drivers = []
    for load, (driven, elapsed, since_break) in zip(loads, _DRIVER_LOGS, strict=True):
        drive_left = min(rules["drive_limit"] - driven, rules["window"] - elapsed)
        break_in = None
        if rules["break_after"] is not None:
            break_in = _fmt(rules["break_after"] - since_break)
        drivers.append(
            {
                "load_id": load.id,
                "driver": load.driver,
                "drive_left": _fmt(drive_left),
                "window_left": _fmt(rules["window"] - elapsed),
                "break_due_in": break_in,
                "status": "out of hours" if drive_left <= 0 else "under 1 hour" if drive_left < 1 else "ok",
            }
        )
    return {"ruleset": ruleset, "label": rules["label"], "drivers": drivers}
