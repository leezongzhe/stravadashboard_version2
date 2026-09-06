import unittest

import pandas as pd

from app.config import DEFAULT_CONFIG
from app.metrics import activity_summary, exact_splits, heart_rate_zones, prepare_trackpoints


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
        data = prepare_trackpoints(self.raw, DEFAULT_CONFIG)
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


if __name__ == "__main__":
    unittest.main()
