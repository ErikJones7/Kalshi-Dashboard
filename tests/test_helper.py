"""Checks for kalshi_helper.py against a fake Kalshi server (no network, no real money, no real keys).
Run:  python3 tests/test_helper.py        (needs the 'cryptography' package only to make a throw-away test key)
It copies the helper into a temporary folder first, so your own data, keys and settings are never touched."""
import sys, os, json, time, threading, base64, shutil, tempfile, importlib.util, urllib.request, urllib.error, http.server
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="kd_test_")
shutil.copy(os.path.join(HERE, "..", "kalshi_helper.py"), os.path.join(TMP, "kalshi_helper.py"))
sys.path.insert(0, TMP)
spec = importlib.util.spec_from_file_location("H", os.path.join(TMP, "kalshi_helper.py"))
H = importlib.util.module_from_spec(spec); sys.modules["H"] = H; spec.loader.exec_module(H)

KEYID = "11111111-2222-3333-4444-555555555555"
KEY = ed25519.Ed25519PrivateKey.generate()
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
STATE = {"bal": 9000, "orders": [], "mode": "fill", "bal_err": False}     # bal is in cents


class Mock(http.server.BaseHTTPRequestHandler):
    def log_message(s, *a): pass
    def _auth(s):
        ts = s.headers.get("KALSHI-ACCESS-TIMESTAMP"); sg = base64.b64decode(s.headers.get("KALSHI-ACCESS-SIGNATURE") or "")
        if s.headers.get("KALSHI-ACCESS-KEY") != KEYID: return False
        try:
            KEY.public_key().verify(sg, (ts + s.command + s.path.split("?")[0]).encode()); return True
        except Exception: return False
    def out(s, code, obj):
        b = json.dumps(obj).encode(); s.send_response(code); s.send_header("Content-Length", str(len(b))); s.end_headers(); s.wfile.write(b)
    def do_GET(s):
        p = s.path.split("?")[0]
        if p.startswith("/trade-api/v2/markets/"):
            close = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 300))
            return s.out(200, {"market": {"ticker": p.split("/")[-1], "status": "active", "close_time": close, "result": "", "yes_ask_dollars": "0.6100", "no_ask_dollars": "0.4000"}})
        if not s._auth(): return s.out(401, {"error": {"message": "bad sig"}})
        if p.endswith("/portfolio/balance"):
            d = STATE["bal"] / 100.0
            return s.out(200, {"balance": STATE["bal"], "balance_dollars": "%.4f" % d, "portfolio_value": 0, "updated_ts": 1,
                               "balance_breakdown": [{"balance": "0.0000", "exchange_index": 0}, {"balance": "%.4f" % d, "exchange_index": 2}]})
        if p.endswith("/portfolio/positions"): return s.out(200, {"market_positions": []})
        if p.endswith("/portfolio/fills"): return s.out(200, {"fills": []})
        if p.endswith("/portfolio/orders"): return s.out(200, {"cursor": "", "orders": []})
        if p.endswith("/portfolio/subaccounts/balances"): return s.out(200, {"subaccount_balances": [{"balance": "%.4f" % (STATE["bal"] / 100.0), "exchange_index": 2, "subaccount_number": 0}]})
        s.out(404, {})
    def do_POST(s):
        body = json.loads(s.rfile.read(int(s.headers.get("Content-Length", "0"))))
        if not s._auth(): return s.out(401, {"error": {"message": "bad sig"}})
        if not s.path.split("?")[0].endswith("/portfolio/events/orders"): return s.out(404, {})
        STATE["orders"].append(body)
        if STATE["mode"] == "insufficient": return s.out(400, {"code": "insufficient_balance", "message": "insufficient balance"})
        if STATE["mode"] == "closed": return s.out(409, {"code": "conflict", "message": "market is closed"})
        if STATE["mode"] == "kill": return s.out(201, {"order_id": "o1", "fill_count": "0.00", "remaining_count": body["count"]})
        px = float(body["price"])
        return s.out(201, {"order_id": "o2", "client_order_id": body.get("client_order_id"), "fill_count": body["count"], "remaining_count": "0.00",
                           "average_fill_price": "%.4f" % px, "average_fee_paid": "0.0100"})


ms = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Mock); threading.Thread(target=ms.serve_forever, daemon=True).start()
MB = "http://127.0.0.1:%d/trade-api/v2" % ms.server_address[1]
H.PROD_BASES = [MB]; H.UPSTREAM = MB; H.DEMO_BASE = MB
hs = H.ThreadingHTTPServer(("127.0.0.1", 0), H.Handler); threading.Thread(target=hs.serve_forever, daemon=True).start()
PORT = hs.server_address[1]
os.makedirs(H.KEYS_DIR, exist_ok=True); open(os.path.join(H.KEYS_DIR, "kalshi.txt"), "w").write(PEM)

FAILS = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: FAILS.append(m)
def call(path, body=None, origin=True):
    h = {"X-Kalshi": "1", "Content-Type": "text/plain"}
    if origin: h["Origin"] = "http://127.0.0.1:%d" % PORT
    elif origin is None: pass
    r = urllib.request.Request("http://127.0.0.1:%d" % PORT + path, data=None if body is None else json.dumps(body).encode(), headers=h, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")
N = [0]
def tk(): N[0] += 1; return "KXBTC15M-26NOV23%02d%02d-%02d" % (12 + N[0] // 4, (N[0] % 4) * 15, (N[0] % 4) * 15)      # a different market each time (one bet per market and mode)
def order(src, ticker, side, count, price, **k):
    time.sleep(0.25); b = {"ticker": ticker, "side": side, "count": count, "price": price, "src": src, "w": time.time() - 100, "conf": 0.95}; b.update(k); return call("/account/order", b)[1]
def set_mode(m): STATE["mode"] = m

# ---- before any setup
st, d = call("/account/status"); ok(st == 200 and d["has_id"] is False, "fresh install: no Key ID yet")
H.save_settings({"kalshi_key_id": KEYID})
st, d = call("/account/status"); ok(d["ready"] and not d["trading"], "key found: account ready, betting still off")
d = order("auto", tk(), "yes", 5, 61); ok(not d["ok"], "order refused while betting is off: " + d.get("error", "")[:70])
st, _ = call("/account/status", origin=None); ok(st in (200, 403), "request without an Origin is handled")
req = urllib.request.Request("http://127.0.0.1:%d/account/status" % PORT, headers={"X-Kalshi": "1", "Origin": "https://evil.example"})
try: urllib.request.urlopen(req); ok(False, "a foreign Origin is refused")
except urllib.error.HTTPError as e: ok(e.code == 403, "a foreign Origin is refused (HTTP %d)" % e.code)

# ---- allocation rules
H.save_settings({"kalshi_key_id": KEYID, "kalshi_trading": True, "kalshi_daily": 1000.0, "kalshi_max_bet": 1000.0})
d = order("auto", tk(), "yes", 5, 61); ok(not d["ok"] and "allocated" in d["error"].lower(), "auto with no allocation is refused: " + d.get("error", "")[:70])
st, d = call("/account/config", {"budget": {"src": "auto", "alloc": 50}}); ok(d.get("ok") and d["budget"]["auto"]["*"]["avail"] == 50, "auto given $50 of the $90 cash")
st, d = call("/account/config", {"budget": {"src": "sim", "key": "BTC", "alloc": 30}}); ok(d.get("ok"), "timed BTC given $30 (total $80)")
st, d = call("/account/config", {"budget": {"src": "sim", "key": "ETH", "alloc": 20}}); ok(not d.get("ok") and "only $10.00 more" in d.get("error", ""), "ETH $20 refused, only $10 of cash is unallocated: " + d.get("error", "")[:80])
d = order("sim", "KXSOL15M-26NOV231200-00", "yes", 2, 50); ok(not d["ok"], "a coin with no bankroll is refused: " + d.get("error", "")[:70])
d = order("auto", tk(), "yes", 100, 61); ok(not d["ok"] and "bankroll" in d["error"], "a bet bigger than its bankroll is refused: " + d.get("error", "")[:80])

# ---- order format and money bookkeeping
T1 = tk(); d = order("auto", T1, "yes", 10, 61); b = STATE["orders"][-1]
ok(d["ok"] and d["filled"] and b["side"] == "bid" and b["price"] == "0.61" and b["count"] == "10.00" and b["time_in_force"] == "fill_or_kill", "YES buy goes out as a V2 bid at 0.61 x10 fill-or-kill")
ok(abs(d["cost"] - (10 * 0.61 + 10 * 0.01)) < 0.001, "YES cost = contracts x price + fee = %.2f" % d["cost"])
d2 = order("auto", tk(), "no", 10, 40); b = STATE["orders"][-1]
ok(d2["ok"] and d2["filled"] and b["side"] == "ask" and b["price"] == "0.60", "NO buy at 40c goes out as a V2 ask at 0.60 (the YES price)")
ok(abs(d2["cost"] - (10 * 0.40 + 10 * 0.01)) < 0.001, "NO cost = contracts x price + fee = %.2f" % d2["cost"])
st, bd = call("/account/budget"); av = bd["budget"]["auto"]["*"]["avail"]
ok(abs(av - (50 - d["cost"] - d2["cost"])) < 0.01, "free bankroll drops by what the two open bets cost: $%.2f" % av)
d = order("auto", T1, "yes", 5, 61); ok(not d["ok"] and "Already bet on this market" in d["error"], "a second bet on the same market from the same mode is refused")
st, d = call("/account/config", {"budget": {"src": "auto", "alloc": 5}}); ok(not d.get("ok") and "hasn't settled" in d.get("error", ""), "allocation can't drop below the money in open bets")

# ---- what Kalshi can answer
set_mode("kill"); d = order("auto", tk(), "yes", 5, 61); ok(d["ok"] and not d["filled"] and "Not filled" in d["message"], "fill-or-kill killed: nothing bought, nothing charged")
set_mode("closed"); d = order("auto", tk(), "yes", 5, 61); ok(not d["ok"] and "market is closed" in d["error"], "Kalshi's 409 text is shown: " + d["error"])
set_mode("insufficient"); T2 = tk(); d = order("auto", T2, "yes", 5, 61)
ok(not d["ok"] and "insufficient balance" in d["error"], "Kalshi's 'insufficient balance' is shown: " + d["error"])
st, bd = call("/account/budget"); ok(abs(bd["budget"]["auto"]["*"]["avail"] - av) < 0.01, "a refused order charges nothing against the bankroll")
rows = [json.loads(l) for l in open(os.path.join(H.DATA, "live_orders.jsonl"))]
ref = [r for r in rows if r["ticker"] == T2]; ok(ref and not ref[-1]["filled"] and "insufficient balance" in (ref[-1].get("refused") or ""), "the refusal is saved in the order log")
set_mode("fill")

# ---- read-only readout of Kalshi's own account data
st, d = call("/account/raw"); ok(st == 200 and d["balance"]["reply"]["balance_breakdown"][1]["exchange_index"] == 2 and "orders" in d["resting_orders"]["reply"] and "subaccount_balances" in d["subaccounts"]["reply"],
                                    "/account/raw returns the balance split by pool, resting orders and sub-account balances")
st, d = call("/account/summary?force=1"); ok(st == 200 and d.get("ok") and abs(d["balance"] - 90.0) < 0.01, "account summary reads the $90.00 balance")

# ---- old backups are tidied: only the newest two are kept
bk = os.path.join(H.HERE, "backup"); os.makedirs(bk, exist_ok=True)
for n in ("2026-11-23a_20261122-204602", "2026-11-23h_20261122-210729", "2026-11-26b_20261124-135944", "2026-11-26k_20261125-173500", "notes"):
    os.makedirs(os.path.join(bk, n), exist_ok=True)
open(os.path.join(bk, "keepme.txt"), "w").write("x")
H.prune_backups()
left = sorted(os.listdir(bk)); ok(left == ["2026-11-26b_20261124-135944", "2026-11-26k_20261125-173500", "keepme.txt", "notes"], "only the newest two backups are kept; other files and folders are left alone: %s" % left)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failed" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
