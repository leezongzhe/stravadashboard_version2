import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH


SCHEMA_VERSION = 2


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
