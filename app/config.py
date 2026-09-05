import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "strava_dashboard_v2.db"
INCOMING_DIR = ROOT_DIR / "incoming"
# Reuse Version 1's known-working authenticated profile when both projects are
# stored together. A standalone Version 2 clone falls back to its own profile.
VERSION_1_BROWSER_DATA_DIR = ROOT_DIR.parent / "version_1" / "browser_data"
BROWSER_DATA_DIR = (
    VERSION_1_BROWSER_DATA_DIR
    if VERSION_1_BROWSER_DATA_DIR.exists()
    else ROOT_DIR / "browser_data"
)
CONFIG_PATH = ROOT_DIR / "config.json"

DEFAULT_CONFIG = {
    "timezone": "Asia/Kuala_Lumpur",
    "resting_heart_rate": 60,
    "maximum_heart_rate": 190,
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
    return config
