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

FAKE AUTO FOLLOWS THE REAL AUTO BET
While real Auto betting is on, a fake Auto bet on the same coin and side as a real one waits for the real order. If the real order fills, the fake bet uses the multiplier Kalshi actually gave the real order (fee included) and takes the same share of the fake bankroll that the real fill was of the real bankroll (so a real bet that only partly filled gives a smaller fake bet too). If the real order is refused or never fills, the fake bet is dropped too, so the fake record doesn't count bets the real account couldn't get. If no real order was attempted (account not ready, no real money left, real betting switched off) or the answer is unknown, the fake bet keeps its own estimated price. The Auto card shows "Real fill copied / skipped" counts. Timed bets are not changed.

AUTO MODE: A SECOND COIN MUST POINT THE OTHER WAY
Auto mode bets one coin per window. It adds a second coin only if that coin points the opposite way (one UP, one DOWN) and passes the same checks as the first: confidence, a steady signal, a safe-estimate edge over the price paid, and a real order-book price. Coins mostly move together, so two bets the same way would usually win or lose together; an UP and a DOWN bet partly offset a market-wide reversal. The two bets share 1.3 times the one-bet size, split evenly, on the fake and the real side.

REAL AUTO AND TIMED ORDERS CAN USE PART OF A CONTRACT
Kalshi sells contracts in pieces as small as 0.01. Real Auto and Timed orders now top the whole contracts up with a fraction, so the bet spends the stake it was sized for (never more than the stake, and never more than the contracts for sale) instead of rounding down to whole contracts. Payouts are therefore no longer whole dollars. If Kalshi ever refuses a fractional count, the same bet is sent again as whole contracts and fractions stay off until the helper is restarted; the order log notes it. Orders you place by hand are unchanged. This needs the helper build 2026-11-26b: close the helper and reopen the dashboard after updating.

EACH AUTO BET NOW KEEPS HOW MANY OTHER COINS AGREED
When Auto mode places a bet, the real order log (data/live_orders.jsonl) records two numbers with it: "agree" (how many other coins qualified for a bet the same way at that moment) and "opp" (how many qualified the opposite way). Nothing in the bot's behavior changes. The numbers are only there so you can check later whether bets where no other coin agreed did worse. This needs the helper build 2026-11-26c: close the helper and reopen the dashboard after updating.

CONTRACTS SHOWN TO 2 DECIMALS
In the real bet history (Auto and Timed) and the all-orders list, the Contracts column now shows two decimals (for example 10.01 or 12.00), since fractional contracts are allowed.

FAKE AUTO CONTROLS ON THE TOP ROW
On the Auto mode card, the fake money row now holds its Start $ box, View bet history and Reset bankroll buttons on the same line as its title, so they are visible without opening the dropdown. Clicking them, or typing in the box, does not fold the dropdown; click the arrow or the title to open or close it.

FAKE TIMED BETS NOW USE ALLOCATED MONEY, WITH AN AUTOMATIC RE-SPLIT
The fake money row on the Timed bets card now works like the real one: a "Total $ for all coins" box with Split evenly, and an "Allocated $" box for each coin. Each coin's allocation is its bankroll and moves with its wins and losses. A coin that loses everything stays at $0 (the old "After a loss: restart" choice is gone). A coin's box can't be changed while it has an unsettled bet.
New: "Re-split at +5%" (the number is adjustable). When the coins' total reaches that many % above the total you last allocated, and no bet is open, the profit is taken and the whole total is split evenly across all the coins again. That also revives any coin that was at $0. Setting a coin's amount, Split evenly and a re-split each move the "last allocated" total, so adding money never counts as profit. Reset all puts each coin back to the amount you last set for it.
The real money Timed bets are unchanged.

FIX: THE FIRST RE-SPLIT LEVEL USES THE MONEY YOU ALLOCATED
The fake Timed bets' "last allocated" total now starts as the sum of the coins' Allocated amounts (what you gave them), not the coins' balances at the moment the feature first ran. Coins already above +5% of that total re-split at the next moment no bet is open.

ONE-TIME CLEAN-UP OF OLD COINS (ADA, BCH, TON)
The first time this build opens, it forgets everything it had stored for ADA, BCH and TON (coins Kalshi no longer lists): their signal history, final calls, calibration samples, practice bankrolls and Auto learning counters, in this browser and in the saved state. It runs once. Their rows in the data folder's CSV and JSONL files were removed separately, with a backup copy kept in data/backup_old_coins.

COINBASE PRICE USED WHENEVER IT IS AVAILABLE
Before, once a coin dropped to a backup price feed (Kraken, OKX or Hyperliquid) after a short Coinbase gap, it stayed on that backup until the backup went quiet, sometimes for minutes, even though Coinbase was back. Now every coin uses Coinbase whenever Coinbase has had a price in the last 15 seconds, and goes back to it the moment it returns. A backup is used only while Coinbase has had nothing for 15 seconds. The Using column in the sources table shows what each coin is on.

CASH-OUT TEST ON THE FAKE AUTO BETS (NOTHING IS SOLD)
Each open fake Auto bet now has its possible early sale checked every second against Kalshi's bid, under six rules: the model flips to the other side at 55, 65, 75 or 85 percent, or the market pays 5 or 10 points more than the model's win chance. When the bet settles, the card shows what each rule would have added or lost compared with holding, net of the selling fee, and how many losers it saved or winners it sold early. It never sells anything and doesn't change any bet or bankroll. Each bet's row in sim_trades.jsonl also keeps when each rule would have fired and the price at that moment (field "co"), so the best rule can be learned from real data later. The bid used is Kalshi's market quote, so very large positions on thin books could get a worse price than shown.

PRICES NOW LINE UP WITH KALSHI'S REFERENCE PRICE
Kalshi settles on a blended reference price (CF Benchmarks) averaged over about 60 seconds, not on the latest Coinbase trade. Measured on 22 hours of your data, the reference sits a small steady distance above Coinbase (about 0 to 8 basis points depending on the coin: BTC about 0, BNB and NEAR about 7). Three changes:
1. Each coin's price is now corrected by its own gap. At every window open the page compares Kalshi's target price with Coinbase's 60-second average just before it (only when that whole minute was priced from Coinbase), keeps the last 20 gaps per coin, and adds the median to the price used everywhere (graph, tables, predictions, bets). It starts from the measured values and replaces them with each coin's own as windows pass. The typical error against Kalshi's target dropped from about 2.2 to 0.8 basis points in testing. The price log's "px" column now holds the corrected price; its Coinbase, Kraken, OKX and Hyperliquid columns stay raw.
2. The graph has a green dotted 60-second average line, and the target card and the coin table show the 60-second average against the target, since that is what Kalshi settles on.
3. Coinbase is used whenever it has a recent price (earlier fix). Other exchanges were tested in a blend and did not improve the match, so they remain backups only.

BUILD 2026-11-26l / HELPER 2026-11-26d: FASTER RETRIES AND ORDER TIMING
- A real Auto or Timed bet that Kalshi refuses only because of the price (not enough for sale, price moved) now looks again after 1 second instead of 3 (RETRY_MS in the page). It still stops when the signal changes, the price isn't worth it, the bankroll is gone, or under 15 seconds are left. The retry cap was raised from 40 to 120 tries so it keeps looking for about as long as before (up to two minutes).
- The helper now records how long each step of every order took, in milliseconds, in the "ms" field of each row in data/live_orders.jsonl: checks, gap (the 0.25 s pause between automatic orders), market (the market lookup), book (the order book lookup), sizing, post (Kalshi's answer to the order) and total.
- The helper changed, so restart it (the page will say so until you do).

BUILD 2026-11-26m: THE REAL AUTO CARD NO LONGER SAYS "WAITING FOR THE REAL BET" WHEN NOTHING IS HAPPENING
- That text was shown whenever the fake Auto bet had been decided but the real order hadn't written a status line yet. Three cases never wrote one: the real account not being ready, the real Auto bankroll having under $1 free, and a bet whose share of the real bankroll came to under $1. In those cases the card sat on "Waiting for the real bet" until the window ended, even though the real bet had already been skipped. Each now says what happened (for example "not placed (its real bankroll is $0.50)").
- The moment a real order is handed over it now shows "checking Kalshi's price", and "(another order is being placed first)" when it is queued behind another real order, instead of staying blank until it reaches Kalshi.
- The helper did not change.

BUILD 2026-11-26n / HELPER 2026-11-26e: CHECK WHETHER YOUR ACCOUNT CAN USE KALSHI'S CF BENCHMARKS VALUES
- Kalshi's 15-minute crypto markets settle on CF Benchmarks index values (BRTI for Bitcoin, and an "..._RTI" index for each other coin), and Kalshi's own API passes those values on to API users. If your account can read them, the app could use the exact numbers Kalshi settles on instead of Coinbase prices plus a learned gap.
- Menu > Kalshi account now has a "Check CF Benchmarks access" button. It makes one read-only call per coin (BTC, ETH, SOL, XRP, DOGE, BNB, HYPE, NEAR, ZEC), takes about 5 seconds, and shows for each coin Kalshi's answer (status), how long it took, the index value, the price the page is using, the difference in basis points, and Kalshi's exact reply if it failed. Nothing is bought, saved or changed, and no bot uses these values yet.
- The helper's list of allowed read-only paths gained /cfbenchmarks/values. Everything else (the only allowed POST, the other GET paths) is unchanged.
- The helper changed, so it restarts by itself when the file is replaced; the page says it is out of date until it has.

BUILD 2026-11-26o / HELPER 2026-11-26f: THE CF BENCHMARKS CHECK NOW MEASURES HOW OLD THE VALUES ARE
- "Check CF Benchmarks access" (Menu > Kalshi account) now runs 3 rounds, a minute apart (about 3 minutes; leave the page open). For every coin and round it shows how old the value is (the time stamp CF puts on it against the moment Kalshi's answer arrived), how far it is from the price this page had at the second it arrived, and how far it is from the price the page had at the value's own time stamp. It also shows the first part of Kalshi's raw reply for BTC, so the layout can be checked.
- A one-line verdict at the top says whether the values are fresh and match the page, fresh but a real distance from it, old (so unusable for live prices), or have no readable time stamp.
- Still read-only: nothing is bought, saved or changed, and no bot uses these values.
- The helper changed (it now reports the time stamps), so it restarts by itself when the file is replaced.

BUILD 2026-11-26p / HELPER 2026-11-26g: FIX FOR THE CF BENCHMARKS CHECK (IT WAS READING THE OLDEST VALUE)
- Kalshi's CF Benchmarks answer is a list of one-second values covering about the last hour, oldest first. The check took the first one, so the values it showed were an hour old (that is why the age read 3600 s, and why the first run's gaps of +12 to +47 bp meant nothing). It now takes the newest value in the list and its own time stamp.
- Compared with the price the page had at the same second, the CF values from the second run were within a few basis points (typically about 2.5 bp) for most coins.
- The helper changed, so it restarts by itself when the file is replaced.

BUILD 2026-11-26q / HELPER 2026-11-26h: LIVE CORRECTION FROM KALSHI'S INDEX (OFF BY DEFAULT)
- The helper now keeps a read-only feed of the CF Benchmarks index values Kalshi's 15-minute crypto markets settle on (BTC, ETH, SOL, XRP, DOGE, BNB, HYPE, NEAR, ZEC). While the page is open it asks Kalshi for each coin about every 10 seconds (about 1 request a second in total; Kalshi allows about 4), keeps the last 10 minutes in memory, and appends every new one-second value to data/cfb-YYYYMMDD.csv.gz (columns t, coin, value; kept 14 days). It slows down or stops by itself if Kalshi says to slow down or says this account can't read the values.
- The page compares those index values with the Coinbase prices it recorded for the same seconds and takes the median difference as each coin's LIVE offset in basis points. With "Correct prices with Kalshi's index (live)" ticked (Menu > Kalshi account), the page adds that live offset to the Coinbase price instead of the offset learned at window opens. The live offset moves at most 3 bp per 10 seconds, is ignored if it looks wrong (over 150 bp), and the page falls back to the learned offset when the live one is older than 45 seconds or when the price isn't coming from Coinbase.
- The tick box is OFF by default. The feed runs and is logged either way, and a status line under the box shows each coin's live offset next to the learned one. Nothing else changes: no bot rule, threshold or bet size.
- The helper changed, so it restarts by itself when the file is replaced.

BUILD 2026-11-26r: SHRINK-AND-EDGE TEST (SHADOW ONLY, NOTHING IS SKIPPED)
- On settled bets the app's predicted chances ran about 5 points too high (about 95% predicted against about 90% that came true on real bets, and 97% against 92% on fake ones, after taking out bets priced from Kraken). A test on past fake bets found that shrinking the chance (95% counts as about 90%, 98% as about 95%) and only betting when the shrunk chance beats the price paid by 4 to 6 points would have kept the better bets: fitted on the first 76 fake bets, it also helped on the next 51 (kept bets averaged +24.7% a bet against +16.5% for all, with a 90% range of +1.9 to +16.0 points for the gain).
- Every fake Auto bet now carries two extra numbers when it is placed: rp (the shrunk chance) and re (the shrunk chance minus the price paid). At settlement the page books what the rule "only bet when re is at least 2, 4 or 6 points" would have kept and dropped, for all fake Auto bets and separately for those that followed a real fill. A table under the cash-out test on the fake Auto card shows, for each setting, how many bets it would keep and drop, with hit rate and return (profit divided by money staked) for each group. rp and re are also saved with each bet in data/sim_trades.jsonl.
- Nothing is skipped and no bet, stake, threshold or real order changes. The helper did not change.

BUILD 2026-11-26s (helper 2026-11-26i): KALSHI CASH GUARD AND RAW ACCOUNT READOUT
- Problem found: since you raised the real Auto allocation, Kalshi has refused every real bet above about $5 with "HTTP 400: insufficient balance" (about 30 refusals from $5.22 to $41.27), while the helper reads a Kalshi balance of $225.15 and your Kalshi app shows it as available. Before the raise, Kalshi accepted bets up to $26.75 without trouble. Kalshi only checks cash when an order would actually fill (your log shows "not enough contracts for sale" refusals come first), so a harmless non-filling test order cannot measure it.
- New safeguard (page): when Kalshi refuses a real Auto bet for insufficient balance, the real Auto card shows a red warning with the smallest refused size, how many were refused in a row and what the app thought was free, and real Auto bets are capped at 60% of the smallest refused size (never below $1, and never below the biggest bet Kalshi has accepted that was smaller than the refusal). The refusal is not retried. A bet near the cap that Kalshi accepts raises the cap by 50%; a bet at least as big as anything refused clears the limit. A "Clear this limit" button clears it by hand. When the page opens it works the limit out from the last 6 hours of the helper's order log, so it is in place straight away. Timed bets are not capped.
- New readout (helper): GET /account/raw shows Kalshi's own raw replies for the balance, the orders still resting (they can lock up cash) and any sub-account balances. It only reads; nothing can place or cancel an order. The helper restarts by itself when the file is replaced.

BUILD 2026-11-26t: CASH LIMIT LIFTED
- The money was moved to the pool Kalshi orders draw on (Kalshi's own balance now shows $222.13 in pool 2 and $0 in pool 0). The $3.13 limit on real Auto bets, and every Kalshi "insufficient balance" refusal from before that moment, are now ignored when the page opens, so real Auto bets size from the allocation again. The safeguard itself stays: if Kalshi refuses a real bet for insufficient balance again, the limit and the red warning come back.

BUILD 2026-11-26u (helper 2026-11-26j): CLEAN-UP, NO CHANGE IN BEHAVIOUR
- Found with ESLint (page) and pyflakes/vulture (helper), then removed: 17 variables the page computed and never used (lastSigHtml, targetOv, fx, bw, bh, sg_, two copies of dd, cp, lv, mG, i, sgn, ev x2, updReady, one unused rows), and from the helper the unused functions book_depth and already_running plus three unused local variables. About 900 characters in total.
- Checked by running 89 older test scripts against the old and new files, each side in its own folder, one test at a time: 123 checks pass and 33 fail on both, and the 33 are old scripts that test behaviour that was changed on purpose. The few differences between runs also appeared between two runs of the old build (clock timing in the tests).
- Looked at and left alone: no two functions in the page have the same body, and in 40 seconds of simulated running the page used about 4% of one CPU core (the busiest function, mc, took about 1% of the time), so nothing was rewritten for speed.
