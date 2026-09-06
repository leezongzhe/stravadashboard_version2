import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import config as app_config
from app import database
from app.config import resolve_maximum_heart_rate, resolve_resting_heart_rate


class HeartRateRecordTests(unittest.TestCase):
    def test_highest_hr_limit_is_persisted(self):
        with tempfile.TemporaryDirectory() as folder:
            config_path = Path(folder) / "config.json"
            with patch.object(app_config, "CONFIG_PATH", config_path):
                app_config.save_config({"highest_hr_activity_limit": 7})
                self.assertEqual(
                    app_config.load_config()["highest_hr_activity_limit"], 7
                )

    def test_automatic_and_manual_sources(self):
        automatic = {
            "resting_heart_rate_mode": "observed",
            "maximum_heart_rate_mode": "observed",
            "fallback_resting_heart_rate": 60,
            "fallback_maximum_heart_rate": 190,
        }
        self.assertEqual(resolve_resting_heart_rate(automatic, 52)[0], 52)
        self.assertEqual(resolve_maximum_heart_rate(automatic, 201)[0], 201)

        manual = {
            **automatic,
            "resting_heart_rate_mode": "manual",
            "manual_resting_heart_rate": 48,
            "maximum_heart_rate_mode": "manual",
            "manual_maximum_heart_rate": 195,
        }
        self.assertEqual(resolve_resting_heart_rate(manual, 52)[0], 48)
        self.assertEqual(resolve_maximum_heart_rate(manual, 201)[0], 195)

    def test_new_extrema_update_current_values_and_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.db"
            with patch.object(database, "DB_PATH", path):
                database.initialize_database()
                with database.connect() as connection:
                    connection.execute(
                        """
                        INSERT INTO activities(
                            activity_id, source, import_status, created_at, updated_at
                        ) VALUES ('one', 'tcx', 'imported', 'now', 'now')
                        """
                    )
                    connection.executemany(
                        """
                        INSERT INTO trackpoints(activity_id, time, heart_rate)
                        VALUES ('one', ?, ?)
                        """,
                        [("2026-01-01T00:00:00Z", 55), ("2026-01-01T00:01:00Z", 180)],
                    )
                    connection.commit()

                first = database.refresh_heart_rate_records(40, 240)
                self.assertEqual(first["observed_minimum"], 55)
                self.assertEqual(first["observed_maximum"], 180)

                with database.connect() as connection:
                    connection.executemany(
                        """
                        INSERT INTO trackpoints(activity_id, time, heart_rate)
                        VALUES ('one', ?, ?)
                        """,
                        [("2026-01-01T00:02:00Z", 50), ("2026-01-01T00:03:00Z", 192)],
                    )
                    connection.commit()

                second = database.refresh_heart_rate_records(40, 240)
                self.assertEqual(second["observed_minimum"], 50)
                self.assertEqual(second["observed_maximum"], 192)
                history = database.heart_rate_record_history()
                self.assertEqual(len(history), 4)


if __name__ == "__main__":
    unittest.main()
