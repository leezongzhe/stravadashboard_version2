import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import pandas as pd

from app import database
from app.importer import import_tcx, parse_tcx
from app.metrics import activity_summary, exact_splits, heart_rate_zones, prepare_trackpoints


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
 <Trackpoint><Time>2026-01-02T00:00:00Z</Time><Position><LatitudeDegrees>3.10</LatitudeDegrees><LongitudeDegrees>101.60</LongitudeDegrees></Position><DistanceMeters>0</DistanceMeters></Trackpoint>
 <Trackpoint><Time>2026-01-02T00:10:00Z</Time><Position><LatitudeDegrees>3.11</LatitudeDegrees><LongitudeDegrees>101.61</LongitudeDegrees></Position><DistanceMeters>1500</DistanceMeters></Trackpoint>
 </Track></Lap></Activity></Activities></TrainingCenterDatabase>"""

MULTI_LAP_SAMPLE = """<?xml version="1.0"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
 <Activities><Activity Sport="Running"><Id>2026-01-03T00:00:00Z</Id>
 <Lap><TotalTimeSeconds>300</TotalTimeSeconds><DistanceMeters>1000</DistanceMeters><Calories>50</Calories><Track>
 <Trackpoint><Time>2026-01-03T00:00:00Z</Time><DistanceMeters>0</DistanceMeters></Trackpoint>
 <Trackpoint><Time>2026-01-03T00:05:00Z</Time><DistanceMeters>1000</DistanceMeters></Trackpoint></Track></Lap>
 <Lap><TotalTimeSeconds>360</TotalTimeSeconds><DistanceMeters>1500</DistanceMeters><Calories>70</Calories><Track>
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

    def test_import_persists_moving_time(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "123.tcx"
            db_path = root / "test.db"
            path.write_text(SAMPLE, encoding="utf-8")
            with mock.patch.object(database, "DB_PATH", db_path):
                status, _ = import_tcx(path)
                with closing(sqlite3.connect(db_path)) as connection:
                    moving_seconds = connection.execute(
                        "SELECT moving_seconds FROM activities WHERE activity_id='123'"
                    ).fetchone()[0]
        self.assertEqual(status, "imported")
        self.assertAlmostEqual(moving_seconds, 10)

    def test_gps_only_activity_remains_analysable_without_heart_rate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gps-only.tcx"
            path.write_text(GPS_ONLY_SAMPLE, encoding="utf-8")
            metadata, points = parse_tcx(path)

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
        self.assertEqual(metadata["distance_m"], 1500)
        self.assertTrue(pd.isna(summary["avg_hr"]))
        self.assertFalse(exact_splits(prepared).empty)
        self.assertTrue(heart_rate_zones(prepared, config).empty)


if __name__ == "__main__":
    unittest.main()
