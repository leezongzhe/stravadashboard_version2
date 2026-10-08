import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app import backup, config, database


class LocalBackupTests(unittest.TestCase):
    def test_round_trip_excludes_browser_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database_path = root / "data" / "dashboard.db"
            incoming = root / "data" / "incoming"
            browser = root / "data" / "browser_data"
            config_path = root / "data" / "config.json"
            backups = root / "backups"
            incoming.mkdir(parents=True)
            browser.mkdir(parents=True)
            incoming.joinpath("123.tcx").write_text("<tcx />", encoding="utf-8")
            browser.joinpath("Cookies").write_text("private", encoding="utf-8")
            config_path.write_text(json.dumps({"timezone": "UTC"}), encoding="utf-8")

            patches = (
                patch.object(config, "DATA_DIR", root / "data"),
                patch.object(config, "DB_PATH", database_path),
                patch.object(config, "INCOMING_DIR", incoming),
                patch.object(config, "BROWSER_DATA_DIR", browser),
                patch.object(config, "CONFIG_PATH", config_path),
                patch.object(database, "DB_PATH", database_path),
            )
            for active_patch in patches:
                active_patch.start()
            try:
                database.initialize_database()
                connection = sqlite3.connect(database_path)
                connection.execute(
                    "INSERT INTO activities(activity_id, source, import_status, created_at, updated_at) "
                    "VALUES ('123', 'tcx', 'imported', 'now', 'now')"
                )
                connection.commit()
                connection.close()

                archive_path = backup.create_backup(True, backups)
                details = backup.inspect_backup(archive_path)
                self.assertEqual(details["tcx_count"], 1)
                self.assertTrue(details["has_database"])
                with zipfile.ZipFile(archive_path) as archive:
                    self.assertFalse(any("browser_data" in name for name in archive.namelist()))

                connection = sqlite3.connect(database_path)
                connection.execute("DELETE FROM activities")
                connection.commit()
                connection.close()
                incoming.joinpath("123.tcx").unlink()
                result = backup.restore_backup(archive_path, make_safety_backup=False)
                self.assertEqual(result["restored_tcx"], 1)
                connection = sqlite3.connect(database_path)
                count = connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
                connection.close()
                self.assertEqual(count, 1)
                self.assertTrue(incoming.joinpath("123.tcx").exists())
                self.assertEqual(browser.joinpath("Cookies").read_text(encoding="utf-8"), "private")
            finally:
                for active_patch in reversed(patches):
                    active_patch.stop()


if __name__ == "__main__":
    unittest.main()
