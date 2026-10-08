import unittest

import pandas as pd

from app.ai_context import build_dashboard_context
from app.config import DEFAULT_CONFIG


class AIContextTests(unittest.TestCase):
    def setUp(self):
        self.activities = pd.DataFrame([
            {
                "activity_id": "today-run",
                "activity_name": "Private home route",
                "activity_type": "Running",
                "start_time": "2026-10-08T00:00:00Z",
                "distance_m": 1000.0,
                "moving_seconds": 600.0,
                "distance_km": 1.0,
            },
            {
                "activity_id": "prior-run",
                "activity_name": "Earlier route",
                "activity_type": "Running",
                "start_time": "2026-10-06T00:00:00Z",
                "distance_m": 1000.0,
                "moving_seconds": 620.0,
                "distance_km": 1.0,
            },
        ])
        self.points = pd.DataFrame({
            "time": pd.date_range("2026-10-08", periods=11, freq="60s", tz="UTC"),
            "latitude": [5.0 + index / 10000 for index in range(11)],
            "longitude": [100.0 + index / 10000 for index in range(11)],
            "altitude": list(range(10, 21)),
            "distance": [index * 100 for index in range(11)],
            "heart_rate": [120 + index * 2 for index in range(11)],
            "speed": [100 / 60] * 11,
        })

    def test_context_matches_dashboard_metrics_and_excludes_coordinates(self):
        config = {
            **DEFAULT_CONFIG,
            "timezone": "UTC",
            "resting_heart_rate": 50,
            "maximum_heart_rate": 190,
            "maximum_moving_gap_seconds": 60,
            "ai_comparison_activity_limit": 1,
        }
        context = build_dashboard_context(
            self.activities,
            lambda _activity_id: self.points.copy(),
            config,
            now=pd.Timestamp("2026-10-08T12:00:00Z"),
        )
        self.assertEqual(context["analysis_scope"], "today")
        self.assertEqual(context["today_activity_count"], 1)
        activity = context["today_activities"][0]
        self.assertAlmostEqual(activity["metrics"]["moving_seconds"], 600)
        self.assertEqual(len(activity["heart_rate"]["zones"]), 5)
        self.assertEqual(len(activity["splits"]), 1)
        self.assertTrue(activity["best_efforts"])
        self.assertTrue(activity["chart_profile_samples"])
        self.assertEqual(activity["activity_name"], "Not shared")
        serialized = str(context).lower()
        self.assertNotIn("latitude", serialized)
        self.assertNotIn("longitude", serialized)
        self.assertNotIn("private home route", serialized)
        self.assertNotIn("database", serialized)

    def test_missing_heart_rate_remains_explicit(self):
        points = self.points.copy()
        points["heart_rate"] = None
        config = {
            **DEFAULT_CONFIG,
            "timezone": "UTC",
            "resting_heart_rate": 60,
            "maximum_heart_rate": 190,
            "maximum_moving_gap_seconds": 60,
            "ai_comparison_activity_limit": 0,
        }
        context = build_dashboard_context(
            self.activities.head(1), lambda _activity_id: points, config,
            now=pd.Timestamp("2026-10-08T12:00:00Z"),
        )
        heart_rate = context["today_activities"][0]["heart_rate"]
        self.assertFalse(heart_rate["available"])
        self.assertEqual(heart_rate["zones"], [])
        self.assertIsNone(context["today_activities"][0]["metrics"]["avg_hr"])

    def test_selected_activity_context_excludes_later_training(self):
        config = {
            **DEFAULT_CONFIG,
            "timezone": "UTC",
            "resting_heart_rate": 50,
            "maximum_heart_rate": 190,
            "maximum_moving_gap_seconds": 60,
            "ai_comparison_activity_limit": 8,
        }
        context = build_dashboard_context(
            self.activities,
            lambda _activity_id: self.points.copy(),
            config,
            selected_activity_id="prior-run",
        )
        self.assertEqual(context["analysis_scope"], "selected_activity")
        self.assertEqual(context["selected_activity_count"], 1)
        self.assertEqual(context["selected_activities"][0]["activity_reference"], "selected-1")
        self.assertEqual(context["training_baselines"][0]["activities"], 1)
        self.assertEqual(context["recent_comparison_activities"], [])


if __name__ == "__main__":
    unittest.main()
