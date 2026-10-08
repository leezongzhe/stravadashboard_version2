import unittest

import pandas as pd

from app.config import DEFAULT_CONFIG
from app.metrics import (
    activity_summary,
    best_efforts,
    exact_splits,
    heart_rate_zones,
    negative_split,
    prepare_trackpoints,
)


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.raw = pd.DataFrame({
            "time": pd.date_range("2026-01-01", periods=11, freq="60s", tz="UTC"),
            "latitude": [5.0] * 11,
            "longitude": [100.0] * 11,
            "altitude": list(range(11)),
            "distance": [value * 100 for value in range(11)],
            "heart_rate": [120 + value for value in range(11)],
            "speed": [100 / 60] * 11,
        })

    def test_summary_and_exact_split(self):
        data = prepare_trackpoints(
            self.raw, {**DEFAULT_CONFIG, "maximum_moving_gap_seconds": 60}
        )
        summary = activity_summary(data)
        splits = exact_splits(data)
        self.assertAlmostEqual(summary["distance_km"], 1.0)
        self.assertAlmostEqual(summary["elapsed_seconds"], 600)
        self.assertEqual(len(splits), 1)
        self.assertAlmostEqual(splits.iloc[0]["Time_seconds"], 600)

    def test_custom_heart_rate_zone_boundaries(self):
        config = {
            **DEFAULT_CONFIG,
            "resting_heart_rate": 50,
            "maximum_heart_rate": 200,
            "zone_upper_percentages": [55, 65, 75, 88, 100],
        }
        data = prepare_trackpoints(self.raw, config)
        zones = heart_rate_zones(data, config)
        self.assertEqual(list(zones["Upper_bpm"]), [132, 148, 162, 182, 200])

    def test_stationary_pause_is_excluded_from_all_pace_calculations(self):
        raw = pd.DataFrame({
            "time": pd.to_datetime([
                "2026-01-01T00:00:00Z", "2026-01-01T00:00:10Z",
                "2026-01-01T00:01:10Z", "2026-01-01T00:01:20Z",
                "2026-01-01T00:01:30Z", "2026-01-01T00:01:40Z",
            ]),
            "latitude": [5.0] * 6,
            "longitude": [100.0] * 6,
            "altitude": [10.0] * 6,
            "distance": [0.0, 250.0, 250.0, 500.0, 750.0, 1000.0],
            "heart_rate": [120, 125, 100, 130, 135, 140],
            # A long recording gap represents a pause even if device speed is
            # stale on the first point after tracking resumes.
            "speed": [25.0] * 6,
        })
        config = {**DEFAULT_CONFIG, "maximum_moving_gap_seconds": 10}
        data = prepare_trackpoints(raw, config)
        summary = activity_summary(data)
        splits = exact_splits(data)
        efforts = best_efforts(data)

        self.assertAlmostEqual(summary["elapsed_seconds"], 100)
        self.assertAlmostEqual(summary["moving_seconds"], 40)
        self.assertAlmostEqual(summary["pace"], 2 / 3)
        self.assertAlmostEqual(splits.iloc[0]["Time_seconds"], 40)
        self.assertAlmostEqual(efforts.loc[efforts["Distance"] == "1 km", "Time_seconds"].iloc[0], 40)
        self.assertAlmostEqual(negative_split(data), 0)
        self.assertAlmostEqual(summary["avg_hr"], 132.5)

    def test_recorded_speed_handles_quantized_distance_samples(self):
        raw = pd.DataFrame({
            "time": pd.date_range("2026-01-01", periods=4, freq="1s", tz="UTC"),
            "latitude": [5.0] * 4,
            "longitude": [100.0] * 4,
            "altitude": [10.0] * 4,
            # The first moving sample has no DistanceMeters increment even
            # though the device reports a valid speed.
            "distance": [0.0, 0.0, 5.0, 10.0],
            "heart_rate": [120, 121, 122, 123],
            "speed": [2.0] * 4,
        })
        data = prepare_trackpoints(raw, DEFAULT_CONFIG)
        self.assertAlmostEqual(activity_summary(data)["moving_seconds"], 3)


if __name__ == "__main__":
    unittest.main()
