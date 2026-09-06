import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

from .config import INCOMING_DIR, load_config
from .database import (
    connect,
    initialize_database,
    record_event,
    refresh_heart_rate_records,
    utc_now,
)


TCX_NS = {
    "tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
    "ext": "http://www.garmin.com/xmlschemas/ActivityExtension/v2",
}


def _text(element, path, namespace=TCX_NS):
    child = element.find(path, namespace)
    return child.text if child is not None else None


def _number(value, converter=float):
    try:
        return converter(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def file_checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def refresh_imported_heart_rate_records():
    config = load_config()
    return refresh_heart_rate_records(
        config.get("minimum_valid_heart_rate", 40),
        config.get("maximum_valid_heart_rate", 240),
    )


def parse_tcx(path):
    path = Path(path)
    root = ET.parse(path).getroot()
    activity = root.find(".//tcx:Activity", TCX_NS)
    if activity is None:
        raise ValueError("TCX does not contain an Activity element")

    lap = activity.find("tcx:Lap", TCX_NS)
    activity_id = path.stem
    sport = activity.attrib.get("Sport", "Unknown")
    start_time = _text(activity, "tcx:Id")
    elapsed = _number(_text(lap, "tcx:TotalTimeSeconds")) if lap is not None else None
    distance = _number(_text(lap, "tcx:DistanceMeters")) if lap is not None else None
    calories = _number(_text(lap, "tcx:Calories")) if lap is not None else None

    points = []
    seen = set()
    for point in activity.findall(".//tcx:Trackpoint", TCX_NS):
        timestamp = _text(point, "tcx:Time")
        key = timestamp
        if key in seen:
            continue
        seen.add(key)
        points.append((
            activity_id,
            timestamp,
            _number(_text(point, "tcx:Position/tcx:LatitudeDegrees")),
            _number(_text(point, "tcx:Position/tcx:LongitudeDegrees")),
            _number(_text(point, "tcx:AltitudeMeters")),
            _number(_text(point, "tcx:DistanceMeters")),
            _number(_text(point, "tcx:HeartRateBpm/tcx:Value"), int),
            _number(_text(point, "tcx:Extensions/ext:TPX/ext:Speed")),
        ))

    if not points:
        raise ValueError("TCX contains no trackpoints")

    if start_time is None:
        start_time = points[0][1]
    if distance is None:
        available = [row[5] for row in points if row[5] is not None]
        distance = max(available) if available else None

    metadata = {
        "activity_id": activity_id,
        "activity_type": sport,
        "start_time": start_time,
        "elapsed_seconds": elapsed,
        "distance_m": distance,
        "calories": calories,
    }
    return metadata, points


def import_tcx(path, force=False):
    """Import one file atomically; a failure leaves prior data untouched."""
    initialize_database()
    path = Path(path)
    checksum = file_checksum(path)

    with connect() as connection:
        existing = connection.execute(
            "SELECT source_checksum, import_status FROM activities WHERE activity_id = ?",
            (path.stem,),
        ).fetchone()
        if (
            not force
            and existing
            and existing["source_checksum"] == checksum
            and existing["import_status"] == "imported"
        ):
            return "unchanged", 0

    try:
        metadata, points = parse_tcx(path)
        now = utc_now()
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM trackpoints WHERE activity_id = ?",
                (metadata["activity_id"],),
            )
            connection.executemany(
                """
                INSERT INTO trackpoints(
                    activity_id, time, latitude, longitude, altitude,
                    distance, heart_rate, speed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                points,
            )
            connection.execute(
                """
                INSERT INTO activities(
                    activity_id, activity_type, start_time, elapsed_seconds,
                    distance_m, calories, source, import_status, retry_count,
                    last_error, source_file, source_checksum, parser_version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'tcx', 'imported', 0, NULL, ?, ?, 2, ?, ?)
                ON CONFLICT(activity_id) DO UPDATE SET
                    activity_type=excluded.activity_type,
                    start_time=excluded.start_time,
                    elapsed_seconds=excluded.elapsed_seconds,
                    distance_m=excluded.distance_m,
                    calories=excluded.calories,
                    source='tcx', import_status='imported', retry_count=0,
                    last_error=NULL, source_file=excluded.source_file,
                    source_checksum=excluded.source_checksum,
                    parser_version=2, updated_at=excluded.updated_at
                """,
                (
                    metadata["activity_id"], metadata["activity_type"],
                    metadata["start_time"], metadata["elapsed_seconds"],
                    metadata["distance_m"], metadata["calories"], path.name,
                    checksum, now, now,
                ),
            )
            record_event(connection, metadata["activity_id"], "imported", path.name)
            connection.commit()
        try:
            refresh_imported_heart_rate_records()
        except Exception as record_error:
            print(f"[WARN] Heart-rate records could not be refreshed: {record_error}")
        return "imported", len(points)
    except Exception as error:
        now = utc_now()
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO activities(
                    activity_id, source, import_status, retry_count, last_error,
                    source_file, created_at, updated_at
                ) VALUES (?, 'tcx', 'parse_failed', 1, ?, ?, ?, ?)
                ON CONFLICT(activity_id) DO UPDATE SET
                    import_status='parse_failed',
                    retry_count=activities.retry_count + 1,
                    last_error=excluded.last_error,
                    source_file=excluded.source_file,
                    updated_at=excluded.updated_at
                """,
                (path.stem, str(error)[:1000], path.name, now, now),
            )
            record_event(connection, path.stem, "parse_failed", str(error)[:1000])
            connection.commit()
        raise


def import_all(force=False):
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    results = {"imported": 0, "unchanged": 0, "failed": 0, "trackpoints": 0}
    for path in sorted(INCOMING_DIR.glob("*.tcx")):
        try:
            status, count = import_tcx(path, force=force)
            results[status] += 1
            results["trackpoints"] += count
            print(f"[OK] {path.name}: {status} ({count:,} trackpoints)")
        except Exception as error:
            results["failed"] += 1
            print(f"[ERROR] {path.name}: {error}")
    # Backfill/rebuild records even when every file was already unchanged.
    refresh_imported_heart_rate_records()
    return results
