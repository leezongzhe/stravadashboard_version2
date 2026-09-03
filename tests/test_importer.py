import tempfile
import unittest
from pathlib import Path

from app.importer import parse_tcx


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


class ImporterTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

