import unittest

import pandas as pd

from app.config import DEFAULT_CONFIG
from app.metrics import activity_summary, exact_splits, prepare_trackpoints


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


if __name__ == "__main__":
    unittest.main()
