# Strava Dashboard — Windows App Edition

This folder is a Windows-only, locally installed form of Version 2. It retains
Version 2's activity analytics and its existing Chrome/Playwright synchronization
mechanism. It does not use the paid or official Strava API.

## What is different

- Double-click `StravaDashboard.exe` to synchronize and open the dashboard.
- First launch lets the user download all activities or the latest chosen number.
- Later launches inspect the newest two Strava training-history pages.
- Training history includes monthly and weekly distance and consistency charts.
- Pace, splits, best efforts, zone time, and training-duration summaries use
  moving time; elapsed and stopped time remain visible for reference.
- The Settings page shows exactly two current all-time HR records: the highest
  valid downloaded HR and the lowest valid downloaded HR.
- Python, Streamlit, and the application dependencies are bundled in the build.
- The database and all private data remain outside the executable.
- A local `.sdbbackup` format backs up the database, settings, and optional TCX files.
- Browser cookies and `browser_data` are never included in a backup.
- A read-only floating AI Coach can analyze the activity currently open through the user's
  own Gemini, OpenAI, Anthropic, or OpenAI-compatible API connection.
- Windows is the only supported platform for this edition.

Google Chrome is still required. On first launch, complete the Strava login in
the Chrome window. The session is retained in this edition's own private browser
profile for subsequent synchronization.

Before that first synchronization, choose either **Download all available
activities** or **Download the latest N activities**. The app follows Strava's
training-history pages until the requested number is found. If N is greater than
the account's total, every available activity is selected. Once setup succeeds,
later launches inspect the newest two pages; unfinished registered downloads
remain in the retry queue.

## Run the packaged app

After building, double-click:

```text
dist\StravaDashboard\StravaDashboard.exe
```

Keep the complete `dist\StravaDashboard` folder together. The main window uses
the bundled `StravaDashboardServer.exe` helper to run the dashboard silently in
the background; users should continue to start only `StravaDashboard.exe`.

The small launcher remains open while synchronization runs and displays progress.
When the local dashboard is ready, it opens in the default browser. Keep the
launcher minimized; closing it stops the local dashboard server.

To open without synchronizing, use PowerShell:

```powershell
.\dist\StravaDashboard\StravaDashboard.exe --dashboard-only
```

## Private data locations

The packaged app stores writable data here:

```text
%LOCALAPPDATA%\StravaDashboardV2App\
  strava_dashboard_v2.db
  config.json
  incoming\
  browser_data\
```

The default backup folder is:

```text
%USERPROFILE%\Documents\Strava Dashboard\Backups\
```

It can be changed in **Settings → Local backup folder**.

## Local backup and recovery

Open the dashboard's **Backup** tab. **Create local backup** writes a timestamped
`.sdbbackup` archive. Leave **Include original TCX files** enabled for a complete
recovery set. You can also download a copy from the dashboard and store it on a
USB drive, NAS, or any normal folder.

For recovery, upload the `.sdbbackup` in the same tab and select **Restore this
backup**. The app validates archive paths, SHA-256 checksums, and SQLite integrity,
then restores everything to the managed data location above. A safety backup of
the current database is created before replacement. The chosen download/upload
location does not become a permanent data dependency.

The authenticated browser profile is intentionally not portable. After restoring
on another computer, sign in to Strava once on that computer.

## Floating AI Coach

Open **Settings → AI coach connection**, choose a provider and model, and enter
your own API key. The key is stored by Windows Credential Manager and is not
saved in the database, `config.json`, local backups, logs, or distributable
folder. Provider/model and privacy preferences are saved normally, but a
restored backup never contains the credential.

The coach appears as a floating bubble at the bottom-right of the dashboard.
Open **Activity analysis**, choose a record, then open the bubble. The coach is
bound to that exact activity page rather than a separate AI report tab. Select
**Prepare current page** to build a read-only snapshot using the same calculation
functions as the visible dashboard: moving and elapsed performance, stopped
time, complete HR-zone distribution, splits, best efforts, pace consistency,
aerobic decoupling, second-half change, elevation, route characteristics, data
quality, chart samples, earlier comparison activities, and 7/28/84-day trends.
Training that happened after the selected activity is excluded from its context.

Review the complete JSON preview and give consent before sending it. Exact GPS
coordinates are never included. Activity names, exact timestamps, and chart samples
can be disabled in Settings. The AI cannot read SQLite directly or change,
delete, synchronize, restore, or otherwise control dashboard data.

AI analysis is generated by an external provider and may be inaccurate. It is
training guidance, not medical diagnosis. Each user is responsible for their
provider account, costs, rate limits, and privacy terms.

## Build on Windows

Python is needed only by the developer who builds the package, not by the person
who runs it. From PowerShell in this folder:

```powershell
.\build_windows.ps1
```

The script creates an isolated build environment and produces a PyInstaller
onedir package in `dist\StravaDashboard`. Distribute that whole folder, not only
the `.exe`, because the adjacent `_internal` folder contains the bundled runtime.

For development without packaging:

```powershell
.\run_source.ps1
```

Source mode keeps test data under `user_data\`, which is ignored by Git. For
automated testing, `STRAVA_DASHBOARD_DATA_DIR` can override the data location.

## Privacy

Never commit or share `user_data`, `browser_data`, `incoming`, databases,
`config.json`, or `.sdbbackup` archives. They may contain routes, timestamps,
heart-rate data, settings, and authenticated sessions. API keys are separate in
Windows Credential Manager, but AI context leaves the computer only after the
user reviews the preview and explicitly consents.
