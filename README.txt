KALSHI DASHBOARD
================
Tracks Kalshi's 15-minute crypto markets (BTC, ETH, SOL, XRP, DOGE, BNB, HYPE, NEAR, ZEC), predicts where each coin ends the
window, and runs Auto mode: fake-money bets always, real-money bets on your Kalshi account when you switch them on.
Statistical estimates, not financial advice.


SETUP AND UPDATES
-----------------
First time (Windows)
  1. Put this folder somewhere permanent.
  2. Double-click "Add Desktop Shortcuts.vbs" once.
  3. Open "Kalshi Dashboard" from your Desktop. It opens in its own window; closing that window closes everything.
  Python 3 must be installed (python.org, tick "Add Python to PATH"). No extra packages are needed.
  Mac / Linux: double-click "Kalshi Dashboard.command".

Updates
  Menu > Updates > "Check for updates" downloads a newer version from the update address and installs it. Your data folder,
  keys folder and settings are never touched. The files being replaced are copied to backup\ first (the newest two copies
  are kept). When the helper's own file changes it restarts itself and the page reloads to match. If the page says the helper
  is out of date, close and reopen the app.

Files
  kalshi_dashboard_v4.html   the dashboard page
  kalshi_helper.py           the helper: talks to Kalshi, places and sells real orders, saves your data
  settings.json              your settings (Key ID, betting on/off, allocations); created by the helper
  keys\                      your Kalshi private key file. Never share this folder or a copy of this folder.
  data\                      everything the app records (see SAVED DATA below)
  backup\                    the files replaced by the last two updates
  app_profile\               the app window's browser profile
  build_exe.bat              optional: builds a single KalshiDashboard.exe


KALSHI ACCOUNT (optional)
-------------------------
Menu > Kalshi account walks you through it: create an API key on kalshi.com (Profile > API Keys), put the private key file
in the keys folder (button in the panel) and paste the Key ID. The private key never leaves this computer and is never sent
to the page. A Demo account option lets you try everything with Kalshi's fake money first. If a key is ever exposed, delete
it on Kalshi's API Keys page.

Real betting is off until you allow it in the Kalshi account panel and then press "Start real betting" on the Auto card.
Both are remembered across restarts and updates; "Stop all real betting" turns everything off at once and nothing restarts
by itself after that. The panel shows your cash, what is allocated, what is currently bet, real wins and losses, the order
list, and an "Activity log" of everything the real-money side did.


AUTO MODE
---------
How a bet is chosen
  - Every second the model gives each coin a probability of finishing the window above Kalshi's target. It simulates price
    paths to the end of the window and averages each path's last 60 seconds, the way Kalshi settles (inside the last minute
    the seconds already gone are real prices). The result is corrected against what has really happened (calibration).
  - Auto bets only against Kalshi's own target for the window, only with 4 minutes or less left, and only when the signal
    has been steady. It pulls the model's number toward how often similar situations really won and subtracts one standard
    error (the "safe estimate").
  - The price is Kalshi's live order book (what an order would really match against), read through the helper, never the
    listed price on the market page, which can lag by 10-25 seconds. If the book can't be read or nothing is for sale, no bet.
  - It bets when the safe estimate beats the price plus Kalshi's fee by enough. Stakes are a fraction of the bankroll (Kelly
    sizing), capped by "Max bet %", and smaller while the bankroll is below its peak.
  - At most two coins per window, and the second must point the opposite way (one UP, one DOWN). The two share 1.3 times the
    one-bet size.

Real money
  - Type an amount in "Allocated $" and press Set. That money is Auto's real bankroll: it moves with its wins and losses, and
    the rest of your Kalshi cash is never touched. Type a smaller number to send money back to your cash, 0 to take it all
    back. It can't go below what is in an unsettled bet.
  - A real bet is placed when the fake-money Auto bets, sized from the real bankroll. Its price limit is the estimated chance
    minus 1 cent, plus "Pay up to N cents extra" (default 1). Orders are immediate-or-cancel: they buy what is for sale at that limit, up to the size, and cancel the rest, so a thin
    book gives a smaller bet instead of none. Hand-placed orders stay fill-or-kill. Fractions of a contract can be bought.
    A bet refused only on price is tried again every second while the signal holds, until about 15 seconds are left.
  - If nothing was for sale (the order filled nothing, or Kalshi had no contracts at the price), Auto stops on that coin for the
    rest of the window, drops its fake twin, and looks for another coin straight away. Every usual check still applies to the new
    pick. It doesn't do this with under 25 seconds left, or when the window's other bet went through.
  - If Kalshi refuses a bet for "insufficient balance", real bets are capped below that size and a red warning appears on the
    Auto card until a bet that big goes through ("Clear this limit" clears it by hand).
  - Contracts you buy yourself in the same market are not counted toward Auto's bankroll or results.
  - Daily and weekly goals: Auto aims for at least +2% a day and +15% a week (Monday to Sunday); both can be changed in the
    real bet history. They never stop betting. After day 5, if the week is behind the straight-line pace, bets are 1.5 times
    normal size until it is back on pace ("Catch-up bet size", 1 turns it off). Bigger bets can lose more.

Fake money
  - Fake Auto runs all the time with its own bankroll (Start $ and Reset bankroll on the card). It mirrors the real bets: when
    a real order fills, the fake bet uses the price Kalshi really gave; when the real order is refused, the fake bet is dropped.
  - Fake bets settle on Kalshi's own result for the market. If Kalshi has no result after 15 minutes, the app's own estimate is
    used and the bet is marked.
  - Market-blend test (table on the fake Auto card, shadow only, nothing is skipped): the model is overconfident exactly when Auto
    bets, because Auto only buys when Kalshi's price is well below the model, and there the market is usually closer to right. Each
    fake bet records the market's chance (the ask for its side), a blended chance (0.65 x market + 0.35 x model) and that minus the
    price paid with the fee. At settlement the table shows what "only bet when the blend beats the price by 0/2/4 points" would have
    kept and dropped, with hit rates and returns, for all fake bets and for those that followed a real fill.
  - Resetting the fake bankroll resets only the bankroll and its win/loss counts. The cash-out, shrink-and-edge and market-blend
    tables, and what Auto has learned, are kept.


EARLY SELLING (real Auto bets)
------------------------------
  - Off until you press "Early selling" on the real Auto card. Tick the rules to use (any ticked rule can sell):
      Flip 55/65/75/85%+   the model now gives the other side at least that much
      Market +5 / +10 pts  what a contract nets at Kalshi's live bid, after the selling fee, is that many points above the
                           model's win chance
    Starting ticks: Flip 65%+ and Market +10 pts.
  - "Do not sell below N c bid": while the bid is under N cents the bet is held. 0 (the start) means no minimum.
  - Sales are judged from the live order book, once a second. Nothing is sold in the last 10 seconds, when the book price is
    over 3 seconds old, or when a contract would net under 5 cents. The order is reduce-only (it can only close what Auto's bet
    holds) and immediate-or-cancel, with a safety floor 10 cents under the bid. A sale that doesn't fill is tried again every
    2 seconds, up to 4 times. A sale whose answer is unclear (a timeout) is never repeated; check Kalshi's own order history.
  - The helper enforces this too: no sale while Early selling is off, it switches off with real betting, and it only sells
    contracts one of this app's own Auto bets bought.
  - Money: a fully sold bet is settled at once by the cash it brought back (a win if more than it cost). A part-sold bet keeps
    the rest until the market settles. The bet history shows "Sold early: profit/loss · would have won/lost if held".
  - The real bet history has an "Early selling, real bets" table: for each rule ticked now, only the sales Auto really made, after
    fees: bets sold, losers saved and winners sold (judged on Kalshi's result), money per bet, the average price sold at, net
    against holding, and how many markets haven't settled yet.
  - Fake Auto keeps testing all six rules on every fake bet (the cash-out table on the fake Auto card). It never sells.


ON SCREEN
---------
  - Kalshi live multipliers card: always shown. It shows the listed price's age when it is 6-20 s old, and "waiting for
    Kalshi's price" when there is none for this window.
  - Best pick: a notification at your chosen times left. A new one replaces the old one, and closing it (X or "Switch to")
    never brings an older one back. The Best pick record card keeps every pick.
  - Real bet history (one per card): only bets that went through, with UP/DOWN, time left when bought, multiplier, result,
    a Selling column (sold, tried and why, or a dash), and 12-hour times. Every attempt is still in data\live_orders.jsonl.
  - While real Auto betting is on, the Auto popup and sound come from the real bet once it is bought.
  - Prices: Coinbase whenever it has had a price in the last 15 seconds; Kraken, OKX or Hyperliquid only while it hasn't.
    Each coin is corrected by its own small, learned gap to Kalshi's reference index (CF Benchmarks). The graph's green dotted
    line is the 60-second average Kalshi settles on.
  - Menu > Kalshi account also has "Check CF Benchmarks access" (read-only) and "Correct prices with Kalshi's index (live)",
    which is off by default.
  - If something in the page fails it is caught and the page keeps running; a "problems caught" note appears next to the build
    number (click it to copy the details).


SAVED DATA (data\ folder)
-------------------------
  live_orders.jsonl          every real order attempt, filled or not, with Kalshi's reason and timing (ms per step)
  live_sells.jsonl           every early sale or try to sell
  exit_log.jsonl             one line per Auto position (real and fake): every second from buy to close (model chance, live
                             order-book bids, listed quote, coin price, volatility, model range and uncertainty), a snapshot
                             at every sale or rule firing, the highest bid after it, and Kalshi's result and settlement value.
                             It changes no decision; it exists to test better sell rules on the prices the bot really saw.
  skip_log.jsonl             one line per window: every 2 s while Auto is looking (4:00 to 0:25 left), each coin the model gives
                             70%+ (confidence, whether its band is trusted, steadiness, live order-book price, learned estimate,
                             cost, edge, and the first check that stopped a bet), Auto's notes and bets, and Kalshi's result per coin.
                             Saved only, never shown; it exists to test which checks can be loosened so fewer windows are skipped.
  sim_trades.jsonl / .csv    fake bets (Auto, and the old Timed bets), with each cash-out rule's firing ("co")
  sim_state.json             fake bankrolls and what Auto has learned
  signals, final_calls, calibration (.csv/.jsonl, calibration_summary.json)   model records used for calibration
  prices-YYYYMMDD.csv.gz     one row per coin per second (exchange prices, top of book, Kalshi's listed quote); kept 14 days.
                             Its Kalshi quote is the lagging listed price (often unchanged for 30 s), so don't judge sell rules
                             on it; use exit_log.jsonl. To stop it: localStorage.setItem("k15pricelog","false") in the console.
  cfb-YYYYMMDD.csv.gz        Kalshi's CF Benchmarks index values; kept 14 days

Timed bets were removed on 2026-11-25. Their saved data is kept unchanged in sim_trades and sim_state.


CHANGELOG (newest first; details are in the GitHub history)
---------
2026-11-26an  market-blend test on fake Auto (shadow only)
2026-11-26am  nothing for sale: Auto drops that coin and looks for another one at once
2026-11-26al  real early-selling table on the bet history
2026-11-26ak  skip log saved for every window; Auto buys take what is for sale instead of all-or-nothing (helper 2026-11-26n)
2026-11-26aj  exit log also records volatility, the model's range and its uncertainty
2026-11-26ai  exit log for every Auto position (helper 2026-11-26m)
2026-11-26ah  Auto prices and sizes bets from the live order book; no fresh listed price needed
2026-11-26ag  minimum bid for early selling
2026-11-26af  closing the best pick notification no longer brings the old one back
2026-11-26ae  sold-early result shows how the bet would have ended if held
2026-11-26ad  only the newest best pick notification stays on screen
2026-11-26ac  bet history shows sales, UP/DOWN, time left when bought, 12-hour times
2026-11-26ab  early-sale safety floor 10 cents under the bid
2026-11-26aa  sales and the fake cash-out test read the live order book (the old cash-out table is kept aside)
2026-11-26z   bet history shows only bets that went through
2026-11-26y   early selling of real Auto bets (helper 2026-11-26l)
2026-11-26x   Kalshi live multipliers card no longer disappears; new markets fetched by name
2026-11-26w   Timed bets removed (data kept)
