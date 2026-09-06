import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH


SCHEMA_VERSION = 3


@contextmanager
def connect():
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
    finally:
        connection.close()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def initialize_database():
    """Create or migrate the database without destroying version-1 data."""
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trackpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id TEXT NOT NULL,
                time TEXT,
                latitude REAL,
                longitude REAL,
                altitude REAL,
                distance REAL,
                heart_rate INTEGER,
                speed REAL
            );

            CREATE TABLE IF NOT EXISTS activities (
                activity_id TEXT PRIMARY KEY,
                activity_name TEXT,
                activity_type TEXT,
                start_time TEXT,
                elapsed_seconds REAL,
                distance_m REAL,
                calories REAL,
                source TEXT NOT NULL DEFAULT 'tcx',
                import_status TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                source_file TEXT,
                source_checksum TEXT,
                parser_version INTEGER NOT NULL DEFAULT 2,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS import_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_hr_extrema (
                activity_id TEXT PRIMARY KEY,
                minimum_hr INTEGER NOT NULL,
                minimum_observed_at TEXT,
                maximum_hr INTEGER NOT NULL,
                maximum_observed_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(activity_id) REFERENCES activities(activity_id)
            );

            CREATE TABLE IF NOT EXISTS heart_rate_record_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_type TEXT NOT NULL CHECK(record_type IN ('minimum', 'maximum')),
                heart_rate INTEGER NOT NULL,
                activity_id TEXT NOT NULL,
                observed_at TEXT,
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_trackpoints_activity_time
                ON trackpoints(activity_id, time);
            CREATE INDEX IF NOT EXISTS idx_activities_start_time
                ON activities(start_time);
            CREATE INDEX IF NOT EXISTS idx_activities_status
                ON activities(import_status);
            """
        )

        # Preserve manual/unavailable records created by the first revision.
        legacy_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='activity_import_status'"
        ).fetchone()
        if legacy_table:
            now = utc_now()
            connection.execute(
                """
                INSERT OR IGNORE INTO activities (
                    activity_id, source, import_status, last_error,
                    created_at, updated_at
                )
                SELECT activity_id, 'manual', status, last_error, ?, ?
                FROM activity_import_status
                """,
                (now, now),
            )

        connection.execute(
            """
            INSERT INTO app_settings(setting_key, setting_value, updated_at)
            VALUES ('schema_version', ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value=excluded.setting_value,
                updated_at=excluded.updated_at
            """,
            (str(SCHEMA_VERSION), utc_now()),
        )
        connection.commit()


def record_event(connection, activity_id, event_type, detail=None):
    connection.execute(
        """
        INSERT INTO import_events(activity_id, event_type, detail, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (str(activity_id), event_type, detail, utc_now()),
    )


def imported_activity_ids():
    with connect() as connection:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT activity_id FROM activities WHERE import_status IN ('imported', 'tcx_unavailable')"
            )
        }


def retryable_activity_ids(retry_limit):
    with connect() as connection:
        return {
            str(row[0])
            for row in connection.execute(
                """
                SELECT activity_id FROM activities
                WHERE import_status IN ('pending', 'temporary_failure', 'parse_failed')
                  AND retry_count < ?
                """,
                (retry_limit,),
            )
        }


def register_discovered(activity_id):
    now = utc_now()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO activities(
                activity_id, source, import_status, created_at, updated_at
            ) VALUES (?, 'strava', 'pending', ?, ?)
            ON CONFLICT(activity_id) DO NOTHING
            """,
            (str(activity_id), now, now),
        )
        connection.commit()


def record_download_failure(activity_id, error, retry_limit):
    """Promote repeated failures to unavailable so they do not loop forever."""
    now = utc_now()
    with connect() as connection:
        row = connection.execute(
            "SELECT retry_count FROM activities WHERE activity_id = ?",
            (str(activity_id),),
        ).fetchone()
        attempts = (row[0] if row else 0) + 1
        status = "tcx_unavailable" if attempts >= retry_limit else "temporary_failure"
        source = "manual" if status == "tcx_unavailable" else "strava"
        connection.execute(
            """
            INSERT INTO activities(
                activity_id, source, import_status, retry_count, last_error,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                source=excluded.source,
                import_status=excluded.import_status,
                retry_count=excluded.retry_count,
                last_error=excluded.last_error,
                updated_at=excluded.updated_at
            """,
            (str(activity_id), source, status, attempts, str(error)[:1000], now, now),
        )
        record_event(connection, activity_id, status, str(error)[:1000])
        connection.commit()
        return status


def reset_failures():
    with connect() as connection:
        connection.execute(
            """
            UPDATE activities
            SET import_status='pending', retry_count=0, last_error=NULL,
                updated_at=?
            WHERE import_status IN ('tcx_unavailable', 'temporary_failure', 'parse_failed')
            """,
            (utc_now(),),
        )
        connection.commit()


def get_app_setting(key, default=None):
    """Read a small internal state value from the dashboard database."""
    with connect() as connection:
        row = connection.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            (str(key),),
        ).fetchone()
    return row[0] if row else default


def set_app_setting(key, value):
    """Persist internal state without placing it in the user's config file."""
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO app_settings(setting_key, setting_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value=excluded.setting_value,
                updated_at=excluded.updated_at
            """,
            (str(key), str(value), utc_now()),
        )
        connection.commit()


def refresh_heart_rate_records(minimum_valid=40, maximum_valid=240):
    """Rebuild activity extrema and append newly established all-time records."""
    minimum_valid = int(minimum_valid)
    maximum_valid = int(maximum_valid)
    if minimum_valid >= maximum_valid:
        raise ValueError("Minimum valid HR must be lower than maximum valid HR")

    now = utc_now()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT tp.activity_id, MIN(tp.heart_rate) minimum_hr,
                   MAX(tp.heart_rate) maximum_hr
            FROM trackpoints tp
            JOIN activities a ON a.activity_id = tp.activity_id
            WHERE a.import_status = 'imported'
              AND tp.heart_rate BETWEEN ? AND ?
            GROUP BY tp.activity_id
            """,
            (minimum_valid, maximum_valid),
        ).fetchall()

        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM activity_hr_extrema")
        extrema = []
        for row in rows:
            activity_id = str(row["activity_id"])
            minimum_hr = int(row["minimum_hr"])
            maximum_hr = int(row["maximum_hr"])
            minimum_time = connection.execute(
                """
                SELECT time FROM trackpoints
                WHERE activity_id = ? AND heart_rate = ?
                ORDER BY time LIMIT 1
                """,
                (activity_id, minimum_hr),
            ).fetchone()
            maximum_time = connection.execute(
                """
                SELECT time FROM trackpoints
                WHERE activity_id = ? AND heart_rate = ?
                ORDER BY time LIMIT 1
                """,
                (activity_id, maximum_hr),
            ).fetchone()
            minimum_observed_at = minimum_time[0] if minimum_time else None
            maximum_observed_at = maximum_time[0] if maximum_time else None
            extrema.append((
                activity_id, minimum_hr, minimum_observed_at,
                maximum_hr, maximum_observed_at, now,
            ))

        connection.executemany(
            """
            INSERT INTO activity_hr_extrema(
                activity_id, minimum_hr, minimum_observed_at,
                maximum_hr, maximum_observed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            extrema,
        )

        current = connection.execute(
            """
            SELECT
                (SELECT MIN(minimum_hr) FROM activity_hr_extrema) observed_minimum,
                (SELECT MAX(maximum_hr) FROM activity_hr_extrema) observed_maximum
            """
        ).fetchone()
        observed_minimum = current["observed_minimum"]
        observed_maximum = current["observed_maximum"]

        prior = connection.execute(
            """
            SELECT
                MIN(CASE WHEN record_type='minimum' THEN heart_rate END) prior_minimum,
                MAX(CASE WHEN record_type='maximum' THEN heart_rate END) prior_maximum
            FROM heart_rate_record_history
            """
        ).fetchone()

        if observed_minimum is not None and (
            prior["prior_minimum"] is None or observed_minimum < prior["prior_minimum"]
        ):
            source = connection.execute(
                """
                SELECT activity_id, minimum_observed_at FROM activity_hr_extrema
                WHERE minimum_hr = ? ORDER BY minimum_observed_at LIMIT 1
                """,
                (observed_minimum,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO heart_rate_record_history(
                    record_type, heart_rate, activity_id, observed_at, recorded_at
                ) VALUES ('minimum', ?, ?, ?, ?)
                """,
                (observed_minimum, source["activity_id"], source["minimum_observed_at"], now),
            )

        if observed_maximum is not None and (
            prior["prior_maximum"] is None or observed_maximum > prior["prior_maximum"]
        ):
            source = connection.execute(
                """
                SELECT activity_id, maximum_observed_at FROM activity_hr_extrema
                WHERE maximum_hr = ? ORDER BY maximum_observed_at LIMIT 1
                """,
                (observed_maximum,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO heart_rate_record_history(
                    record_type, heart_rate, activity_id, observed_at, recorded_at
                ) VALUES ('maximum', ?, ?, ?, ?)
                """,
                (observed_maximum, source["activity_id"], source["maximum_observed_at"], now),
            )

        connection.commit()
        return {
            "observed_minimum": int(observed_minimum) if observed_minimum is not None else None,
            "observed_maximum": int(observed_maximum) if observed_maximum is not None else None,
            "activities_with_hr": len(extrema),
        }


def heart_rate_record_history(limit=100):
    with connect() as connection:
        return connection.execute(
            """
            SELECT record_type, heart_rate, activity_id, observed_at, recorded_at
            FROM heart_rate_record_history
            ORDER BY recorded_at DESC, id DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()


def activity_heart_rate_extrema(limit=100):
    with connect() as connection:
        return connection.execute(
            """
            SELECT e.activity_id, a.start_time, e.minimum_hr, e.maximum_hr,
                   e.minimum_observed_at, e.maximum_observed_at
            FROM activity_hr_extrema e
            LEFT JOIN activities a ON a.activity_id = e.activity_id
            ORDER BY e.maximum_hr DESC, a.start_time DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
