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

BETS YOU ADD BY HAND
  If you buy more contracts yourself in a market Auto or Timed bets already bet in, only the contracts the app itself bought count toward its
  net, allocation and free-to-bet. Your own contracts are not credited to it, win or lose.

DAILY AND WEEKLY GOALS (real Auto mode)
  Auto aims for at least +2% a day and +15% over the week (Monday to Sunday). Open "View real bet history" on the Auto card to see today's
  and this week's settled profit as a share of the bankroll at the start of that day or week, whether each minimum is met, and the last
  7 days one by one. The two minimums can be changed there in the "Day min" and "Week min" boxes. They are targets, not guarantees. Auto never stops betting because of
  them, and the daily minimum never changes a bet; the weekly minimum only changes bet size as described next.
  Weekly catch-up: for the first 5 days of the week Auto bets as normal. From the end of day 5, if the week's return is behind the
  straight-line pace to the weekly minimum (for example +10.7% by the end of day 5 for +15%), Auto bets 1.5 times its normal amount
  (and its Max bet limit is raised by a quarter) until the week is back on pace, then it goes back to normal. The size is the
  "Catch-up bet size" box in the bet history (1 turns it off). Bigger bets can lose more, so this is riskier, not safer.

AUTO'S PRICE CHECK
  Before Auto decides to bet, it asks the helper for the price an order would really match against (Kalshi's order book), not just the
  quoted price on the market page, and works out its edge and multiplier from that. If nothing is for sale on the side it wants, it skips
  that coin. If the helper can't read the book, it falls back to the quoted price as before.

FAKE TIMED BETS ARE PRICED LIKE A REAL FILL
  A fake Timed bet used to take the quoted price with no fee and bet the whole bankroll at that price, however few contracts were for sale. Now
  it is priced the way a real order would be: it reads Kalshi's order book (through the helper), buys the cheapest level first and works
  upward, adds Kalshi's fee, and only bets what is actually for sale (the rest of that coin's bankroll stays put until the bet settles). If the
  book can't be read, or in a practice run, it uses the quoted price plus the fee. The Timed card shows the date this started and a separate
  tally of the bets since then, because earlier Timed results used the old pricing and look better than a real fill would. The real Timed bet
  no longer waits for the fake one's price. (This needs the new helper build, 2026-11-25f; the page tells you if the helper must be restarted.)

FAKE BETS USE KALSHI'S OWN TARGET AND KALSHI'S OWN RESULT
  Auto and Timed bets (fake and real) are only placed against Kalshi's own target number for the window; if Kalshi's number hasn't loaded yet,
  the bet waits. When a window closes, a fake bet is no longer judged by the app's own 60-second average: it waits for Kalshi's result for that
  market ("waiting for Kalshi" is shown on the card) and is settled on that. A window's Auto bets settle together. If Kalshi has not published
  a result after 15 minutes, the bet is settled on the app's own estimate instead and is marked as such. The Timed and Auto cards show how many
  bets were settled on Kalshi's result and how many times it differed from the app's own estimate. Closing the page while a bet is waiting
  drops that bet (its bankroll is left as it was).

PRICE LOG (for testing better models later)
  While the helper is running, the page sends it one row per coin per second to data\prices-YYYYMMDD.csv.gz (one compressed file per UTC
  day, about 5-10 MB a day, the last 14 days are kept): the combined price, each exchange's own price, the best bid / ask and their sizes
  on OKX and Coinbase, and Kalshi's quote and target. Nothing in the app reads it. It exists so alternative models can be compared on
  exactly what the page saw. To stop it, type  localStorage.setItem("k15pricelog","false")  in the browser console.

NOTIFICATIONS
  While real Auto betting is on, the Auto popup and sound come from the real bet (when its order is actually bought), not from the
  fake-money one. With real Auto betting off, the fake-money Auto bet still notifies as before.

REFRESH RATE
  In the last 4 minutes of every window the dashboard refreshes every coin's Kalshi price twice a second (once a second before that).
  If Kalshi says there are too many requests, it drops back to once a second for a minute and carries on.

PRICES
  A real bet is only placed when its price is at or below what the model thinks it is worth (minus 1 cent). The "Pay up to N cents extra"
  box on Auto mode and Timed bets lets it pay a little more so more bets go through (default 1; 0 is the strictest). A refused bet says
  why in the activity log. On Timed bets, a coin whose leftover is too small to bet (under $1) after a loss goes to $0 and the
  leftover returns to your cash.
  If a real Auto mode or Timed bets order is refused only because the price is not there yet, it keeps looking every few seconds until
  the window is nearly over, as long as the signal still holds and the price is still worth paying. (A Timed bet that retries is placed
  later than its "Bet at" time.)

KEEPING GOING
  If something in the page ever fails, it is caught and the page keeps running; a "problems caught" note appears next to the build number
  (click it to copy the details). Price feeds that go silent reconnect on their own, and requests that never answer time out.

COINS
  ADA, BCH and TON are no longer tracked. Any money that was allocated to them goes back to your cash automatically.

FILES
  kalshi_helper.py            the helper (fetches Kalshi data, saves your data)
  kalshi_dashboard_v4.html    the dashboard page
  keys\                       your Kalshi private key file (only if you connect your account; never share this folder)
  data\                       created on first run: signals, final calls, calibration, simulated bets (CSV files)
  build_exe.bat               optional: builds a single KalshiDashboard.exe

THE START REAL BETTING BUTTONS ARE REMEMBERED
Auto mode and Timed bets each have a Start real betting button. Whatever you left them on (or off) is saved in settings.json, so closing the app, restarting it or updating it puts them back the way they were. Only your own presses change what is remembered. Switching all real betting off in Menu, Kalshi account forgets both, and nothing restarts by itself after that: you press Start again. If the account isn't ready or there is no real money allocated when the app comes back, it says so in the real-betting log and leaves the button off. The first time you update to this version the buttons start off, because the older version did not remember anything.
