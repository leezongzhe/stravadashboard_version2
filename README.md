# Strava Dashboard — Version 2

Version 2 keeps the original project intact and provides a more reliable synchronization and analytics pipeline.

## Main improvements

- First-run Strava login is built into synchronization.
- The working Google Chrome login mechanism and saved profile from version 1 are reused.
- Existing TCX files are imported deterministically without a folder watcher.
- Downloads and imports are tracked in SQLite.
- Repeatedly unavailable/manual activities stop retrying automatically.
- Failed activities can be explicitly retried.
- Imports are transactional and safe to repeat.
- TCX checksums prevent unnecessary re-imports.
- Historical, comparison, route, split, best-effort, HR-zone and quality views are included.
- Altitude is smoothed before elevation and grade calculations.

## First-time setup

Open PowerShell in this folder and run:

```powershell
.\setup.ps1
```

If PowerShell blocks local scripts, run the commands manually:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Normal execution

```powershell
.\run_dashboard.ps1
```

Version 2 uses the same Strava discovery, TCX download, and persistent-session
approach as Version 1. It always stores its private browser profile in
`browser_data/` and never reads Version 1's profile.

For first login, Version 2 starts the installed Chrome executable normally and
then attaches the synchronization controller through Chrome's debugging endpoint.
It presses Strava's Google login control when present, lets you complete any
account or two-factor prompt, and saves the resulting session for later runs.
Close other Chrome windows using the Version 2 profile before synchronization.

Google Chrome and Python 3.10 or newer are required.

## Useful modes

```powershell
# Import copied/local TCX files without accessing Strava
.\.venv\Scripts\python.exe launcher.py --local-only

# Open the dashboard without synchronizing
.\.venv\Scripts\python.exe launcher.py --dashboard-only

# Retry activities previously marked unavailable or failed
.\.venv\Scripts\python.exe launcher.py --retry-failed
```

## Personal configuration

Copy the example configuration and then edit your private copy:

```powershell
Copy-Item config.example.json config.json
```

Edit `config.json` to set the timezone, resting heart rate, maximum heart rate, movement thresholds, altitude smoothing, and automatic retry limit. `config.json` is excluded from Git because it may contain personal values.

## Data and privacy

The repository excludes `browser_data`, `incoming`, all TCX and SQLite database files, virtual environments, and `config.json`. These contain authenticated sessions, precise routes, activity timestamps, heart-rate readings, or other personal values and must not be committed.
