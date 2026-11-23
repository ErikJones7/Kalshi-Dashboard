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
  and is never sent to the dashboard page. Betting stays OFF until you press the "Real betting" button in the Kalshi
  account panel. There are no per-bet or per-day limits: each mode can only bet the money you allocated to it. Only 15-minute crypto markets can be bought, as fill-or-kill orders. Every bet attempt is
  recorded in data\live_orders.jsonl. Use the Demo account option to try it with fake money first.
  REAL-MONEY VIEWS: the Timed bets card and the Auto mode card each have a "Real money" button that swaps the card for a
  real-money version that looks and works like the fake-money one. Type an amount in its Allocated $ box (Auto mode: one box;
  Timed bets: one per coin, or the "Total $ for all coins" box at the top, which splits that total evenly across every coin, even if some coins already have money) and press Set or Enter. That money is its bankroll: it can only bet that amount,
  and the amount goes up and down with its wins and losses. The rest of your Kalshi cash is never touched (for example $50 of a
  $90 account leaves $40 untouched). If it wins $10 the box shows $60; type 50 and press Set and the extra $10 goes back to your
  cash. Type a bigger number to add more (never more than your free cash), or 0 to take everything back. The amount can't go
  below what is in a bet that hasn't settled. Then press "Start real betting" once.
  Real bets are placed only when the fake-money twin bets, and a mode can never bet more than its allocated money. They switch off whenever you
  restart, and "Stop all real betting" turns everything off at once. The Kalshi account card shows your cash, what is allocated,
  what is currently bet, and your real wins and losses (taken from Kalshi's own market results). Once a real bet has gone through, the helper replaces its own estimates with Kalshi's records: the price and fee actually paid, the
  multiplier that gives, and the payout when the market settles. Real wins, losses, net and bankroll use those figures.
  Each card has its own "View real bet history" button (what was bought, the price paid, multiplier, result and payout).
  The Start/Stop real betting button sits next to the "Real money" label on each card.
  The Auto mode and Timed bets cards show the real-money version at all times, with the fake-money version in a dropdown at the bottom.
  The "Activity log" button in the
  Kalshi account panel opens a card with everything the real-money modes did, with times.
  The helper restarts itself when its program file is replaced (for example by an update), and the page reloads to match it.
  The key can place real bets: keep the keys folder private and never share it or the zip of this folder. If a key is ever exposed,
  delete it on Kalshi's API Keys page.

MAC / LINUX
  Double-click "Kalshi Dashboard.command" (needs Python 3). Updating works the same way.

COINS
  ADA, BCH and TON are no longer tracked. Any money that was allocated to them goes back to your cash automatically.

FILES
  kalshi_helper.py            the helper (fetches Kalshi data, saves your data)
  kalshi_dashboard_v4.html    the dashboard page
  keys\                       your Kalshi private key file (only if you connect your account; never share this folder)
  data\                       created on first run: signals, final calls, calibration, simulated bets (CSV files)
  build_exe.bat               optional: builds a single KalshiDashboard.exe
