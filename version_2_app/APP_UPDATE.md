# Version 2 App — Update and Repack Notes

Last updated: 7 September 2026

This document is the maintenance handoff for `version_2_app`. Read it before
changing features or creating another Windows package. The current local backup
design is accepted as the baseline and should be preserved in future releases.

## Scope of this edition

- Target platform: Windows only.
- User interface: the Version 2 Streamlit dashboard, launched as a local app.
- Distribution: PyInstaller **onedir** package.
- Synchronization: the existing Version 2 Chrome/Playwright mechanism.
- Strava API: not used.
- Cloud backup or Google Drive API: not used.
- Personal database and browser data: external to the packaged executable.
- The independent `version_2` folder must remain unchanged when developing this edition.

At the time of this update, these synchronization files were byte-identical:

```text
version_2/app/sync.py
version_2_app/app/sync.py
SHA-256: 7CC2E18D6F42C588869E528FCD511A055691814E692071C3499930D27146DC4C
```

Do not replace synchronization with the official Strava API or silently change
its browser/login behaviour during an ordinary app feature update. Treat that as
a separate, explicitly requested project.

## Files introduced or changed

### `app/config.py`

Code and writable data are separated. In a packaged build, private data is stored at:

```text
%LOCALAPPDATA%\StravaDashboardV2App\
  strava_dashboard_v2.db
  config.json
  incoming\
  browser_data\
```

In source mode, data is stored under `version_2_app/user_data`. Tests can override
the location with `STRAVA_DASHBOARD_DATA_DIR`.

The default local backup directory is:

```text
%USERPROFILE%\Documents\Strava Dashboard\Backups\
```

The user can override it through the `backup_directory` setting.

### `app/backup.py`

This module defines the accepted local backup implementation. Backups use the
`.sdbbackup` suffix and are ZIP containers with this logical structure:

```text
manifest.json
data/database.sqlite       optional when no database exists
data/config.json           optional when no settings exist
data/incoming/*.tcx        optional, controlled by the user
```

`manifest.json` currently records:

- backup format version;
- UTC creation time;
- application name;
- whether TCX files were requested;
- SHA-256 checksum for every declared payload;
- explicit exclusion of `browser_data`.

The SQLite file is produced with SQLite's online backup API instead of copying a
possibly active database file. This is important because the live database uses
WAL mode.

### `dashboard.py`

A **Backup** tab was added. It provides:

- creation of timestamped local backups;
- optional inclusion of original TCX files;
- browser download of a created archive;
- a list of the ten most recent local backups;
- upload and inspection of a `.sdbbackup` file;
- explicit restore action;
- an automatic safety backup before replacing current data;
- display of the managed application-data location.

The Settings tab contains the configurable local backup folder.

### `launcher_app.py`

This is the Windows entry point. It:

1. opens a small native progress window;
2. runs existing synchronization on a worker thread;
3. streams synchronization messages into the window;
4. starts the packaged Streamlit server as a hidden child process;
5. binds the server to `127.0.0.1` only;
6. opens the dashboard in the user's default browser;
7. stops the local server when the launcher closes.

Use `--dashboard-only` to start the dashboard without synchronizing. The internal
`--serve-dashboard --port <port>` mode is used by the launcher and smoke tests.

## Backup validation and unrelated files

The upload control filters for `.sdbbackup`, but extension filtering is not the
security boundary. Renamed or unrelated files are rejected by backend validation.

Before restoration, the current implementation verifies:

- the input is a readable ZIP archive;
- `manifest.json` exists;
- the backup format number is supported;
- archive paths are not absolute and do not contain `..` traversal;
- all manifest-declared payloads exist;
- every declared payload matches its SHA-256 checksum;
- the archive does not contain a `data/browser_data/` payload;
- a supplied database passes `PRAGMA quick_check`;
- the database contains the required `activities` and `trackpoints` tables;
- a supplied settings file contains valid JSON.

Only after validation does restoration replace the database/settings and merge
TCX files into the canonical `incoming` directory. Existing SQLite `-wal` and
`-shm` sidecars are removed immediately before database replacement. If a current
database exists, the system first creates a complete safety backup.

The browser profile is deliberately never backed up or restored. A user restoring
onto another computer must sign in to Strava once on that computer.

### Possible future hardening

The current backup method is considered good enough for continued feature work.
If backups later accept files from untrusted public sources, consider adding:

- maximum archive upload size;
- maximum decompressed byte count;
- maximum TCX file count and individual TCX size;
- rejection of undeclared archive members;
- duplicate ZIP-member detection;
- stricter settings-schema validation.

These are future defensive improvements, not blockers for the present local-use design.

## Windows packaging

Build configuration is stored in `StravaDashboardV2App.spec`. It deliberately
creates an onedir package because the Streamlit assets, Playwright runtime, and
scientific Python dependencies need to remain together. Distribute the entire
folder, not the executable alone.

The specification must continue to include:

- `dashboard.py` as bundled data;
- Streamlit, Plotly, and PyDeck data files;
- distribution metadata for Streamlit, Plotly, PyDeck, Playwright, Pandas,
  NumPy, and Altair;
- hidden imports for modules loaded by the dashboard data script;
- `streamlit.runtime.scriptrunner.magic_funcs` explicitly.

The last item is essential. Without it, the server starts but the dashboard fails
when a browser session executes the bundled script.

Build from PowerShell:

```powershell
Set-Location version_2_app
.\build_windows.ps1
```

The script uses Python 3.13 to create `.build_venv`, installs
`requirements-build.txt`, and produces:

```text
dist\StravaDashboard\StravaDashboard.exe
```

The build script checks `$LASTEXITCODE` after dependency and PyInstaller commands.
Keep these checks; PowerShell does not automatically turn every failed external
program into a terminating error.

After validation, create the distributable archive with:

```powershell
Compress-Archive -LiteralPath .\dist\StravaDashboard `
  -DestinationPath .\dist\StravaDashboard-Windows-x64.zip `
  -CompressionLevel Optimal -Force
```

The package created for this update passed testing and was archived as:

```text
dist\StravaDashboard-Windows-x64.zip
```

## Required checks after every feature update

### 1. Compile and unit tests

Run the test suite with `version_2_app` on `PYTHONPATH`:

```powershell
$env:PYTHONPATH=(Resolve-Path .).Path
python -m unittest discover -s .\tests -v
Remove-Item Env:PYTHONPATH
```

The accepted baseline is eight passing tests, including the backup round trip in
`tests/test_backup.py`. Add tests when new behaviour is introduced; do not reduce
the expected test count merely to make packaging pass.

### 2. Source-server health check

Start the internal server on a temporary port and temporary data directory. Check:

```text
http://127.0.0.1:<port>/_stcore/health
```

It must return `ok`, and the root page must return HTTP 200.

### 3. Packaged browser-render test

A health endpoint alone is insufficient because Streamlit does not fully execute
the dashboard script until a browser connects. After building, start:

```powershell
.\dist\StravaDashboard\StravaDashboard.exe --serve-dashboard --port 8767
```

Then run:

```powershell
.\.build_venv\Scripts\python.exe .\package_smoke_test.py http://127.0.0.1:8767
```

Expected output:

```text
Packaged dashboard rendered successfully.
```

Use a temporary `STRAVA_DASHBOARD_DATA_DIR` during smoke tests. Stop the test
server afterward and remove only the synthetic test-data directory.

### 4. Privacy audit

Before sharing or publishing a package, verify it contains none of these:

```text
*.db
*.db-wal
*.db-shm
*.tcx
config.json
browser_data
Cookies
*.sdbbackup
```

Do not include `user_data`, `.build_venv`, or `build` in a release archive.
Only `dist\StravaDashboard` should be distributed.

### 5. Version 2 preservation check

Run:

```powershell
git -C ..\version_2 status --short
Get-FileHash ..\version_2\app\sync.py, .\app\sync.py -Algorithm SHA256
```

The Version 2 status should be empty. Unless synchronization was explicitly part
of the new request, both synchronization hashes should remain equal.

## Current verified state

For this update:

- all eight automated tests passed;
- backup creation and restore passed a database/TCX round trip;
- browser data remained untouched and excluded;
- the source local server returned a healthy response;
- the packaged EXE started on `127.0.0.1`;
- the packaged dashboard rendered successfully in headless Chrome;
- no personal database, TCX, settings, cookies, or backup archive was included;
- the `version_2` Git working tree remained clean.

When future features are complete, repeat the build and every verification step
above before replacing the distributable ZIP.

## Update: weekly trends and selectable first download

Implemented and repackaged on 7 September 2026.

### Functional changes

- Training history now shows weekly distance and weekly activity consistency in
  addition to the existing monthly charts.
- A first-launch native dialog asks the user to download all Strava activities
  or enter a positive number for the latest N activities.
- The pagination code stops once N newest unique activities have been collected.
  When N is greater than Strava's reported total, pagination reaches the final
  page and selects every available activity.
- The successful first-time choice is stored in SQLite `app_settings` under
  `initial_download_setup_complete` and `initial_download_selection`. Normal
  launches then inspect only page one. Registered historical downloads that were
  interrupted remain eligible for retry.
- Cancelling the first-launch choice opens the dashboard without synchronization
  and leaves setup incomplete, so the choice appears again next launch.
- The multi-lap TCX parser correction and GPS-without-heart-rate handling from
  the functional Version 2 edition were carried into the app package.

This update explicitly changed the app synchronization orchestration and
pagination. It did not replace Chrome/Playwright, the login workflow, download
URL, retry policy, or private app-specific browser profile with the Strava API.
The independent `version_2` folder received only the requested weekly charts and
matching README note.

### Backup and private-data invariants

The accepted local backup format and restore behavior were not changed. In
particular:

- `.sdbbackup` remains a checksummed ZIP container;
- SQLite's online backup API remains in use;
- restoration still validates archive paths, checksums, database integrity and
  required tables before changing current data;
- a safety backup is still made before replacement;
- `browser_data` is never included or restored;
- database, config, TCX, browser profile, and backups remain outside the package.

`app/backup.py` was not edited during this update. Its verified SHA-256 is:

```text
F0ABA5F755B6543FC9148FB1849758499A85167D7B522D0806A0B309DF63918A
```

### Verification for this package

- 16 app unit tests passed, including backup round trip, bounded first download,
  N greater than total, download all, routine page-one scan, multi-lap TCX and
  GPS-only activity coverage.
- All 14 functional Version 2 tests passed after its weekly-chart-only change.
- Python compilation checks passed for the launcher, dashboard and changed app
  modules.
- The PyInstaller onedir build completed successfully.
- The packaged local server returned `ok` from `/_stcore/health`.
- The packaged dashboard completed the Playwright browser-render smoke test.
- A package privacy scan found no database, WAL/SHM file, TCX, config, browser
  profile, cookie, user-data folder, or `.sdbbackup` payload.

Continue to build with `build_windows.ps1` and distribute the entire
`dist\StravaDashboard` folder or the corresponding Windows x64 ZIP.

Verified distributable from this update:

```text
File: dist\StravaDashboard-Windows-x64.zip
Size: 141,499,269 bytes
SHA-256: 75E30891CE4B9A431AA0A39955C281C1E139A777C6723D9212635086B9799F82
```

### HR record display correction

The app dashboard previously rendered every historical step stored in
`heart_rate_record_history`, so an account could show many rows such as 171,
174, 178 and 196 bpm. The functional dashboard appeared to show only two because
its separate database contained fewer historical steps.

The app now deterministically displays exactly two current records:

- the greatest valid `maximum` HR record;
- the smallest valid `minimum` HR record.

Ties use the most recently recorded matching row, and both rows retain their
activity-analysis links. Historical changes remain stored in SQLite for audit
and future features; only their dashboard presentation is reduced. The backup
format and backup/restore implementation remain unchanged.

## Moving-time analytics and two-page routine sync

Implemented on 8 October 2026.

- GPS distance changes are now the authoritative movement signal whenever
  consecutive trackpoints contain distance. A stale positive TCX speed value
  can no longer turn a stationary pause into moving time.
- Every prepared activity now has per-interval moving time and cumulative moving
  time. The primary pace, exact splits, best efforts, second-half pace change,
  average HR, and heart-rate zone durations exclude stationary intervals.
- Elapsed time and stopped time remain available as descriptive values, while
  history totals and grouped duration summaries use persisted moving time.
- Database schema version 4 adds `activities.moving_seconds`. Parser version 4
  causes existing TCX files to be reprocessed once so this value is backfilled;
  no original TCX or private data is deleted.
- After first-time setup, synchronization now inspects the newest two Strava
  training-history pages. The first-time Download N/Download All behavior is
  unchanged.

The accepted `.sdbbackup` format, restore validation, private-data paths,
browser profile, and login workflow were not changed.

The Windows build now contains a console-subsystem
`StravaDashboardServer.exe` helper beside the windowed launcher. The launcher
starts this helper with `CREATE_NO_WINDOW`, so users still see only the normal
launcher UI. This avoids missing-standard-stream failures in the packaged
Streamlit process. The entire `dist\StravaDashboard` folder must remain
together; users continue to open only `StravaDashboard.exe`.

Verification for this update:

- 19 focused tests passed: 13 importer/metrics/database/backup tests and 6
  pagination tests.
- Python compilation checks passed.
- The packaged helper returned `ok` from `/_stcore/health`, and the Chrome
  render smoke test found the expected dashboard navigation.
- The package privacy scan found no database, TCX, backup, browser profile,
  incoming folder, or user-data payload.
- `app/backup.py` remains unchanged at SHA-256
  `F0ABA5F755B6543FC9148FB1849758499A85167D7B522D0806A0B309DF63918A`.

Current Windows x64 distributable:

```text
File: dist\StravaDashboard-Windows-x64.zip
Size: 162,974,053 bytes
SHA-256: 429A02B97E46BA3B7296411D1ACB1397349928A1CA193914DEDBB3D01CC6E35E
```

### Moving-time correction for quantized TCX distance

Corrected on 8 October 2026 after validating the reported activity against its
raw TCX samples.

The first moving-time revision made cumulative `DistanceMeters` authoritative.
That assumption was incorrect for this device: the file contains nearly
one-second samples and valid positive device speed, but `DistanceMeters` remains
unchanged for many individual samples because it is stored in coarse steps. The
dashboard consequently reduced the correct 53:35 moving time to 46:33.

Movement detection now:

1. uses positive device-recorded TCX speed when available;
2. falls back to distance-derived speed when recorded speed is absent;
3. still rejects timestamp gaps above `maximum_moving_gap_seconds`, so paused
   gaps are excluded.

Parser version 5 forces the local TCX collection to be reprocessed once. For the
reported 10.01 km activity, the corrected calculation is 3,215 seconds (53:35),
while elapsed time remains 3,296 seconds (54:56). Backup behavior and private
data locations remain unchanged.
