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

KALSHI ACCOUNT AND LIVE BETTING (optional)
  Menu > Kalshi account walks you through it: create an API key on kalshi.com (Profile > API Keys), put the private key file
  Kalshi gives you in the "keys" folder (button in the panel), and paste the Key ID. The private key never leaves this computer
  and is never sent to the dashboard page. Betting stays OFF until you switch it on, and the helper enforces a per-bet and a
  per-day limit (fees included). Only 15-minute crypto markets can be bought, as fill-or-kill orders. Every bet attempt is
  recorded in data\live_orders.jsonl. Use the Demo account option to try it with fake money first.
  REAL-MONEY REPLICAS: the Timed bets card and the Auto mode card each have a "Real money" switch. When on, every time that
  mode bets, the same bet (same coin, side and moment) is also placed on your Kalshi account. Simulated bets use the "Real stake $"
  box; Auto mode uses its own sizing rules applied to your account value. They switch off whenever you restart, and the "Stop all real
  betting" button turns everything off at once. The Kalshi account card shows your cash, what is currently bet, today's spend and
  your real wins and losses (taken from Kalshi's own market results).
  The key can place real bets: keep the keys folder private and never share it or the zip of this folder. If a key is ever exposed,
  delete it on Kalshi's API Keys page.

MAC / LINUX
  Double-click "Kalshi Dashboard.command" (needs Python 3). Updating works the same way.

FILES
  kalshi_helper.py            the helper (fetches Kalshi data, saves your data)
  kalshi_dashboard_v4.html    the dashboard page
  keys\                       your Kalshi private key file (only if you connect your account; never share this folder)
  data\                       created on first run: signals, final calls, calibration, simulated bets (CSV files)
  build_exe.bat               optional: builds a single KalshiDashboard.exe
