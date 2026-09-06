import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.importer import parse_tcx
from app.metrics import activity_summary, exact_splits, heart_rate_zones, prepare_trackpoints, quality_report


SAMPLE = """<?xml version="1.0"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
 xmlns:ext="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
 <Activities><Activity Sport="Running"><Id>2026-01-01T00:00:00Z</Id>
 <Lap StartTime="2026-01-01T00:00:00Z"><TotalTimeSeconds>10</TotalTimeSeconds>
 <DistanceMeters>20</DistanceMeters><Track>
 <Trackpoint><Time>2026-01-01T00:00:00Z</Time><DistanceMeters>0</DistanceMeters>
 <Extensions><ext:TPX><ext:Speed>2</ext:Speed></ext:TPX></Extensions></Trackpoint>
 <Trackpoint><Time>2026-01-01T00:00:10Z</Time><DistanceMeters>20</DistanceMeters>
 <HeartRateBpm><Value>120</Value></HeartRateBpm>
 <Extensions><ext:TPX><ext:Speed>2</ext:Speed></ext:TPX></Extensions></Trackpoint>
</Track></Lap></Activity></Activities></TrainingCenterDatabase>"""

GPS_ONLY_SAMPLE = """<?xml version="1.0"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
 <Activities><Activity Sport="Running"><Id>2026-01-02T00:00:00Z</Id>
 <Lap StartTime="2026-01-02T00:00:00Z"><TotalTimeSeconds>600</TotalTimeSeconds>
 <DistanceMeters>1500</DistanceMeters><Track>
 <Trackpoint><Time>2026-01-02T00:00:00Z</Time><Position><LatitudeDegrees>3.10</LatitudeDegrees><LongitudeDegrees>101.60</LongitudeDegrees></Position><AltitudeMeters>20</AltitudeMeters><DistanceMeters>0</DistanceMeters></Trackpoint>
 <Trackpoint><Time>2026-01-02T00:10:00Z</Time><Position><LatitudeDegrees>3.11</LatitudeDegrees><LongitudeDegrees>101.61</LongitudeDegrees></Position><AltitudeMeters>25</AltitudeMeters><DistanceMeters>1500</DistanceMeters></Trackpoint>
 </Track></Lap></Activity></Activities></TrainingCenterDatabase>"""

MULTI_LAP_SAMPLE = """<?xml version="1.0"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
 <Activities><Activity Sport="Running"><Id>2026-01-03T00:00:00Z</Id>
 <Lap StartTime="2026-01-03T00:00:00Z"><TotalTimeSeconds>300</TotalTimeSeconds><DistanceMeters>1000</DistanceMeters><Calories>50</Calories><Track>
 <Trackpoint><Time>2026-01-03T00:00:00Z</Time><DistanceMeters>0</DistanceMeters></Trackpoint>
 <Trackpoint><Time>2026-01-03T00:05:00Z</Time><DistanceMeters>1000</DistanceMeters></Trackpoint>
 </Track></Lap>
 <Lap StartTime="2026-01-03T00:05:00Z"><TotalTimeSeconds>360</TotalTimeSeconds><DistanceMeters>1500</DistanceMeters><Calories>70</Calories><Track>
 <Trackpoint><Time>2026-01-03T00:11:00Z</Time><DistanceMeters>2500</DistanceMeters></Trackpoint>
 </Track></Lap></Activity></Activities></TrainingCenterDatabase>"""


class ImporterTests(unittest.TestCase):
    def test_multi_lap_metadata_uses_all_laps(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "multi-lap.tcx"
            path.write_text(MULTI_LAP_SAMPLE, encoding="utf-8")
            metadata, points = parse_tcx(path)
        self.assertEqual(len(points), 3)
        self.assertEqual(metadata["distance_m"], 2500)
        self.assertEqual(metadata["elapsed_seconds"], 660)
        self.assertEqual(metadata["calories"], 120)

    def test_parse_tcx(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "123.tcx"
            path.write_text(SAMPLE, encoding="utf-8")
            metadata, points = parse_tcx(path)
        self.assertEqual(metadata["activity_id"], "123")
        self.assertEqual(metadata["activity_type"], "Running")
        self.assertEqual(metadata["distance_m"], 20)
        self.assertEqual(len(points), 2)
        self.assertEqual(points[-1][6], 120)

    def test_gps_only_activity_remains_analysable_without_heart_rate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gps-only.tcx"
            path.write_text(GPS_ONLY_SAMPLE, encoding="utf-8")
            metadata, points = parse_tcx(path)

        self.assertEqual(metadata["distance_m"], 1500)
        self.assertTrue(all(point[6] is None for point in points))
        frame = pd.DataFrame(
            points,
            columns=[
                "activity_id", "time", "latitude", "longitude", "altitude",
                "distance", "heart_rate", "speed",
            ],
        )
        config = {
            "altitude_smoothing_points": 3,
            "moving_speed_threshold_mps": 0.5,
            "maximum_moving_gap_seconds": 700,
            "resting_heart_rate": 60,
            "maximum_heart_rate": 190,
            "zone_upper_percentages": [60, 70, 80, 90, 100],
        }
        prepared = prepare_trackpoints(frame, config)
        summary = activity_summary(prepared)
        self.assertAlmostEqual(summary["distance_km"], 1.5)
        self.assertTrue(pd.isna(summary["avg_hr"]))
        self.assertTrue(pd.isna(summary["max_hr"]))
        self.assertFalse(exact_splits(prepared).empty)
        self.assertTrue(heart_rate_zones(prepared, config).empty)
        self.assertEqual(quality_report(prepared)["missing_hr_percent"], 100.0)


if __name__ == "__main__":
    unittest.main()
