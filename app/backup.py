"""Portable, local backups for user-owned dashboard data.

Browser cookies and the Chrome profile are deliberately excluded. A backup can
contain the SQLite database, settings, and optionally the original TCX files.
"""

import hashlib
import io
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from . import config


BACKUP_FORMAT = 1
BACKUP_SUFFIX = ".sdbbackup"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _database_snapshot():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="strava-dashboard-backup-") as folder:
        snapshot = Path(folder) / "database.sqlite"
        source = sqlite3.connect(config.DB_PATH)
        destination = sqlite3.connect(snapshot)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return snapshot.read_bytes()


def create_backup(include_tcx=True, destination_dir=None):
    """Create an immutable local archive and return its absolute path."""
    destination = Path(destination_dir or config.default_backup_directory()).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output = destination / f"strava-dashboard-{stamp}{BACKUP_SUFFIX}"
    counter = 1
    while output.exists():
        output = destination / f"strava-dashboard-{stamp}-{counter}{BACKUP_SUFFIX}"
        counter += 1

    payloads = {}
    if config.DB_PATH.exists():
        payloads["data/database.sqlite"] = _database_snapshot()
    if config.CONFIG_PATH.exists():
        payloads["data/config.json"] = config.CONFIG_PATH.read_bytes()
    if include_tcx and config.INCOMING_DIR.exists():
        for path in sorted(config.INCOMING_DIR.glob("*.tcx")):
            payloads[f"data/incoming/{path.name}"] = path.read_bytes()

    manifest = {
        "format": BACKUP_FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "application": "Strava Dashboard Version 2 App",
        "includes_tcx": bool(include_tcx),
        "files": {name: _sha256(data) for name, data in payloads.items()},
        "excludes": ["browser_data"],
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, data in payloads.items():
            archive.writestr(name, data)
    return output


def _read_archive(source):
    if isinstance(source, (str, Path)):
        archive = zipfile.ZipFile(source, "r")
    else:
        archive = zipfile.ZipFile(io.BytesIO(source), "r")
    with archive:
        names = archive.namelist()
        if "manifest.json" not in names:
            raise ValueError("This file is not a Strava Dashboard backup.")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe path found in backup archive.")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != BACKUP_FORMAT:
            raise ValueError("Unsupported backup format.")
        expected = manifest.get("files", {})
        payloads = {}
        for name, checksum in expected.items():
            if name not in names:
                raise ValueError(f"Backup is missing {name}.")
            data = archive.read(name)
            if _sha256(data) != checksum:
                raise ValueError(f"Checksum validation failed for {name}.")
            payloads[name] = data
        if any(name.startswith("data/browser_data/") for name in names):
            raise ValueError("Backup unexpectedly contains private browser data.")
    return manifest, payloads


def inspect_backup(source):
    manifest, payloads = _read_archive(source)
    return {
        **manifest,
        "tcx_count": sum(name.startswith("data/incoming/") for name in payloads),
        "has_database": "data/database.sqlite" in payloads,
        "has_settings": "data/config.json" in payloads,
    }


def _validate_database(data):
    with tempfile.TemporaryDirectory(prefix="strava-dashboard-restore-") as folder:
        candidate = Path(folder) / "database.sqlite"
        candidate.write_bytes(data)
        connection = sqlite3.connect(candidate)
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()[0]
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            connection.close()
    if result != "ok" or not {"activities", "trackpoints"}.issubset(tables):
        raise ValueError("The backup database is damaged or incompatible.")


def restore_backup(source, make_safety_backup=True):
    """Validate then restore into the canonical app data directory."""
    manifest, payloads = _read_archive(source)
    database_data = payloads.get("data/database.sqlite")
    if database_data is not None:
        _validate_database(database_data)

    safety_path = None
    if make_safety_backup and config.DB_PATH.exists():
        safety_path = create_backup(include_tcx=True)

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if database_data is not None:
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{config.DB_PATH}{suffix}")
            if sidecar.exists():
                sidecar.unlink()
        temporary = config.DB_PATH.with_suffix(".restore.tmp")
        temporary.write_bytes(database_data)
        temporary.replace(config.DB_PATH)
    settings = payloads.get("data/config.json")
    if settings is not None:
        json.loads(settings.decode("utf-8"))
        temporary = config.CONFIG_PATH.with_suffix(".restore.tmp")
        temporary.write_bytes(settings)
        temporary.replace(config.CONFIG_PATH)
    config.INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    restored_tcx = 0
    for name, data in payloads.items():
        if name.startswith("data/incoming/"):
            filename = PurePosixPath(name).name
            if not filename.lower().endswith(".tcx"):
                continue
            (config.INCOMING_DIR / filename).write_bytes(data)
            restored_tcx += 1
    return {
        "created_at": manifest["created_at"],
        "restored_tcx": restored_tcx,
        "safety_backup": safety_path,
    }
