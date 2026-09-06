import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "strava_dashboard_v2.db"
INCOMING_DIR = ROOT_DIR / "incoming"
# Version 2 owns its browser profile. It never reads or writes Version 1 data.
BROWSER_DATA_DIR = ROOT_DIR / "browser_data"
CONFIG_PATH = ROOT_DIR / "config.json"

DEFAULT_CONFIG = {
    "timezone": "Asia/Kuala_Lumpur",
    "resting_heart_rate_mode": "observed",
    "manual_resting_heart_rate": None,
    "fallback_resting_heart_rate": 60,
    "maximum_heart_rate_mode": "observed",
    "manual_maximum_heart_rate": None,
    "fallback_maximum_heart_rate": 190,
    "zone_upper_percentages": [60, 70, 80, 90, 100],
    "minimum_valid_heart_rate": 40,
    "maximum_valid_heart_rate": 240,
    "moving_speed_threshold_mps": 0.5,
    "maximum_moving_gap_seconds": 10,
    "altitude_smoothing_points": 15,
    "automatic_retry_limit": 2,
}


def load_config():
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            config.update(json.load(handle))
    # `maximum_heart_rate` existed before the settings page. Keep it available
    # as a fallback without treating the old template value as a manual choice.
    if config.get("fallback_maximum_heart_rate") is None:
        config["fallback_maximum_heart_rate"] = config.get("maximum_heart_rate", 190)
    if config.get("fallback_resting_heart_rate") is None:
        config["fallback_resting_heart_rate"] = config.get("resting_heart_rate", 60)
    return config


def save_config(updates):
    """Persist private user settings atomically while preserving unknown keys."""
    config = load_config()
    config.update(updates)
    config.pop("maximum_heart_rate", None)
    config.pop("resting_heart_rate", None)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_PATH.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")
    temporary.replace(CONFIG_PATH)
    return config


def resolve_maximum_heart_rate(config, observed_maximum=None):
    """Return the active maximum HR and an auditable source label."""
    mode = config.get("maximum_heart_rate_mode", "observed")
    manual = config.get("manual_maximum_heart_rate")
    if mode == "manual" and manual is not None:
        return int(manual), "Manual setting"
    if observed_maximum is not None:
        return int(observed_maximum), "Highest downloaded TCX record"
    fallback = config.get("fallback_maximum_heart_rate", 190)
    return int(fallback), "Fallback until HR data is imported"


def resolve_resting_heart_rate(config, observed_minimum=None):
    """Return the active resting HR and an auditable source label."""
    mode = config.get("resting_heart_rate_mode", "observed")
    manual = config.get("manual_resting_heart_rate")
    if mode == "manual" and manual is not None:
        return int(manual), "Manual setting"
    if observed_minimum is not None:
        return int(observed_minimum), "Lowest downloaded TCX activity record"
    fallback = config.get("fallback_resting_heart_rate", 60)
    return int(fallback), "Fallback until HR data is imported"
