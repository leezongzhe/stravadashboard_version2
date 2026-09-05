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

Version 2 uses the same login mechanism as Version 1: Playwright launches the
installed Google Chrome executable with a persistent profile. Version 2 always
uses its own private `browser_data/` folder and never reads Version 1's browser
profile. Complete authentication once in the visible browser; later runs reuse
the saved Version 2 session.

For a completely new profile, Google may reject sign-in from an automated browser
with a “Couldn't sign you in” message. Version 2 therefore leaves the login page
under your control instead of automatically pressing the Google button. Use
direct Strava credentials when available. This restriction comes from Google's
OAuth security policy, not from the dashboard database or synchronization logic.

Google Chrome is attempted first, exactly as in Version 1. Playwright Chromium is
used as a fallback. Python 3.10 or newer is recommended.

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
