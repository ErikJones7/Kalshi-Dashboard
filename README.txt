KALSHI DASHBOARD
================

FIRST TIME (Windows)
  1. Unzip this folder somewhere permanent (for example Documents\KalshiDashboard).
  2. Double-click "Add Desktop Shortcuts.vbs" once.
  3. Open "Kalshi Dashboard" from your Desktop. It opens in its own window; closing that window
     closes everything. Nothing else to start or stop.
  Python must be installed (python.org, tick "Add Python to PATH").

UPDATING (no new setup)
  Download the new zip and unzip it over this same folder, replacing the files when asked.
  Your Desktop icons keep working. Your saved data (the "data" folder) is never touched.
  If an old version is still running, the new one replaces it automatically.

MAC / LINUX
  Double-click "Kalshi Dashboard.command" (needs Python 3). Updating works the same way.

FILES
  kalshi_helper.py            the helper (fetches Kalshi data, saves your data)
  kalshi_dashboard_v4.html    the dashboard page
  data\                       created on first run: signals, final calls, calibration, simulated bets (CSV files)
  build_exe.bat               optional: builds a single KalshiDashboard.exe
