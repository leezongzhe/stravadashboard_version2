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
- A Settings page controls personal HR zones and analysis thresholds.
- Lowest/highest valid TCX heart rates are recorded dynamically and used by
  default until the user selects manual resting or maximum HR values.

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

Use the dashboard's **Settings** tab to set the timezone, automatic or manual
resting/maximum HR sources, five HR-zone limits, valid sensor range, movement
threshold, recording-gap limit, altitude smoothing, and download retry limit.
The private values are saved to `config.json`, which is excluded from Git.

The timezone field is a searchable worldwide selector built dynamically from the
installed IANA timezone database. Options use region/city names and show their
current UTC offsets, including applicable daylight-saving rules.

## Dynamic heart-rate records and zones

Version 2 stores per-activity HR minima/maxima and an all-time record history in
SQLite. After each TCX import it rebuilds the current extrema. A higher valid HR
becomes the automatic maximum; a lower valid activity HR becomes the automatic
resting input. Manual settings override either automatic value independently.

“Highest-HR activities” includes imported activities that contain at least one
heart-rate sample inside the valid sensor range configured in Settings. For each
activity, the dashboard takes its single highest valid TCX sample, sorts the
activities from highest to lowest, and shows the user-selected top N. The top-N
control can range from one to the total number of imported activities containing
valid HR data. The first use defaults to all available activities; after the user
chooses N, that value is saved in private `config.json` and becomes the default
for future sessions. Equal maxima are ordered by activity date. Both this list
and the all-time record history include links that open and preselect the
corresponding Activity analysis.

Zones use the heart-rate-reserve calculation:

```text
zone boundary = resting HR + percentage × (maximum HR − resting HR)
```

The default upper percentages are 60%, 70%, 80%, 90%, and 100%, and all five can
be customized. The lowest exercise HR is not necessarily a true physiological
resting HR, so a measured morning, sleep, or clinical value is preferable when
available.

## Data and privacy

The repository excludes `browser_data`, `incoming`, all TCX and SQLite database files, virtual environments, and `config.json`. These contain authenticated sessions, precise routes, activity timestamps, heart-rate readings, or other personal values and must not be committed.
