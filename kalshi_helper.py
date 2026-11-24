#!/usr/bin/env python3
"""
Kalshi helper + one-time installer for the 15-minute crypto dashboard
=====================================================================

WHAT IT DOES
  * Runs a tiny program on your own computer that (1) serves the dashboard page and
    (2) fetches Kalshi's public market data for it (browsers block the page from doing that itself).
  * It only listens on 127.0.0.1 (your computer), only forwards read-only public Kalshi data,
    and never touches your Kalshi account or any keys.

ONE-TIME SETUP (then you just click the desktop icon, or nothing at all)
    python kalshi_helper.py --install
  This creates a "Kalshi Dashboard" icon on your Desktop and makes the helper start by itself
  every time you log in. To undo it:   python kalshi_helper.py --uninstall

EVERYDAY USE
    Double-click the "Kalshi Dashboard" icon. The dashboard opens in its own app window (using Edge, Chrome
    or Brave, no tabs or address bar) and the helper stops by itself when you close that window.
    Add --tab to use a normal browser tab instead.

RUNNING IT BY HAND (no install)
    python kalshi_helper.py            starts it and opens the dashboard
    python kalshi_helper.py --no-browser

DATA FOLDER
  The helper saves every scored signal, final call and calibration sample to a folder called
  "data" next to this file (signals.csv, final_calls.csv, calibration.csv, calibration_summary.json,
  plus .jsonl copies). Open the .csv files in Excel / Google Sheets any time.

Keep this file and kalshi_dashboard_v4.html together in one permanent folder (the installer
remembers where they are). Python 3.7+ is the only requirement; no extra packages.
"""
import argparse
import collections
import csv
import gzip
import hashlib
import http.client
import json
import math

HELPER_BUILD = "2026-11-26c"      # the page compares this with its own build to spot a helper that was updated but not restarted
import os
import platform
import re
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("KALSHI_UPSTREAM", "https://api.elections.kalshi.com/trade-api/v2").rstrip("/")
FROZEN = bool(getattr(sys, "frozen", False))            # True when running as the packaged .exe
HERE = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
BUNDLE = getattr(sys, "_MEIPASS", HERE)                 # where PyInstaller unpacks the bundled dashboard page
ALLOWED = ("/markets", "/series", "/events", "/exchange")   # read-only public data only
CACHE_TTL = 0.4                                             # seconds; avoids hammering Kalshi
DEFAULT_PORT = 8787
cache = {}
lock = threading.Lock()
START_T = time.time()
UPDATE_EXT = (".py", ".html", ".txt", ".vbs", ".command")
bye_at = [0.0]               # set when the dashboard window/tab says it is closing
last_active = [0.0]          # last time the dashboard page talked to us (ignores plain /ping checks)
TAB = [False]                # --tab opens a normal browser tab instead of an app window
KEEP = [False]               # --keep-running disables auto-exit
IDLE_AFTER_PAGE = 300        # seconds with no dashboard activity before the helper closes itself
IDLE_NEVER_USED = 600        # ... or if no dashboard ever connected

# --------------------------------------------------------------------------- data folder
DATA = os.path.join(HERE, "data")
SIG_COLS = ["window_end_utc", "window_end_epoch", "coin", "call", "model_prob", "raw_prob", "secs_left",
            "target_price", "kalshi_up_multiplier", "kalshi_down_multiplier", "called_side_multiplier",
            "kalshi_yes_ask", "kalshi_yes_bid", "settled_above_target", "result"]
SIM_COLS = ["window_end_utc", "window_end_epoch", "coin", "checkpoint_secs", "call", "model_prob", "secs_left",
            "target_price", "kalshi_yes_ask", "kalshi_yes_bid", "multiplier", "stake", "settled_above_target",
            "result", "payout", "profit", "bankroll_after"]
FIN_COLS = ["window_end_utc", "window_end_epoch", "coin", "call", "confidence", "predicted_final",
            "target_price", "secs_left", "settled_above_target", "result",
            "kalshi_up_multiplier", "kalshi_down_multiplier", "called_side_multiplier", "kalshi_yes_ask", "kalshi_yes_bid", "selected_coin"]
CAL_COLS = ["window_start_epoch", "coin", "second_epoch", "raw_logit", "outcome_above"]
store = {"sig": [], "fin": [], "sim": []}
seen = {"sig": set(), "fin": set(), "sim": set()}
cal_recent = collections.deque(maxlen=15000)
cal_seen = collections.deque(maxlen=60000)
cal_seen_set = set()
CAL_COUNT = [0]


def rkey(r):
    return hashlib.sha1(json.dumps(r, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def iso(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts))


def sig_row(r):
    import math
    w = int(r.get("w", 0)) + 900
    tgt = math.exp(r["anchorLn"]) if r.get("anchorLn") is not None else ""
    return [iso(w), w, r.get("sym"), r.get("side"), round(r.get("p", 0), 5), round(r.get("raw", 0), 5), r.get("tau"),
            round(tgt, 8) if tgt != "" else "", rd(r.get("mUp")), rd(r.get("mDn")), rd(r.get("m")),
            r.get("ask", ""), r.get("bid", ""), int(bool(r.get("up"))), "HIT" if r.get("hit") else "MISS"]


def sim_row(r):
    import math
    w = int(r.get("w", 0)) + 900
    tgt = math.exp(r["anchorLn"]) if r.get("anchorLn") is not None else ""
    return [iso(w), w, r.get("sym"), r.get("cp"), r.get("side"), round(r.get("p", 0), 5), r.get("tau"),
            round(tgt, 8) if tgt != "" else "", r.get("ask", ""), r.get("bid", ""), rd(r.get("mult")),
            rd(r.get("stake")), int(bool(r.get("up"))), "WIN" if r.get("hit") else "LOSS",
            rd(r.get("payout")), rd(r.get("pnl")), rd(r.get("bank"))]


def rd(v):
    return "" if v is None else round(v, 4)


def fin_row(r):
    import math
    w = int(r.get("w", 0)) + 900
    tgt = math.exp(r["anchorLn"]) if r.get("anchorLn") is not None else ""
    return [iso(w), w, r.get("sym"), r.get("side"), round(r.get("p", 0), 5), round(r.get("final", 0), 8),
            round(tgt, 8) if tgt != "" else "", r.get("tau"), int(bool(r.get("up"))), "HIT" if r.get("hit") else "MISS",
            rd(r.get("mUp")), rd(r.get("mDn")), rd(r.get("m")), r.get("ask", ""), r.get("bid", ""),
            "" if r.get("sel") is None else int(bool(r.get("sel")))]


def read_simstate():
    try:
        with open(os.path.join(DATA, "sim_state.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_csv(name, cols, rows):
    tmp = os.path.join(DATA, name + ".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    os.replace(tmp, os.path.join(DATA, name))


def cal_key(r):
    return (r.get("w"), r.get("s"), r.get("t"), r.get("x"), r.get("y"))


def log(msg):
    """Append to helper.log next to this file so problems are visible even when running hidden."""
    try:
        with open(os.path.join(HERE, "helper.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


CSVS = {"sig": ("signals.csv", SIG_COLS, sig_row), "fin": ("final_calls.csv", FIN_COLS, fin_row), "sim": ("sim_trades.csv", SIM_COLS, sim_row)}
csv_stale = set()       # spreadsheets that must be rebuilt in full because the last write to them failed (for example, open in Excel)


def rewrite_csvs():
    for kind, (name, cols, fn) in CSVS.items():
        if store[kind]:
            try:
                write_csv(name, cols, [fn(r) for r in store[kind]])
                csv_stale.discard(kind)
            except Exception:
                csv_stale.add(kind)
                log("could not rewrite %s (will retry on the next save):\n%s" % (name, traceback.format_exc()))


def append_csv(kind, rows):
    """Add the new rows to the end of the spreadsheet instead of rewriting every row each time; rebuild in full if anything looks off."""
    name, cols, fn = CSVS[kind]
    path = os.path.join(DATA, name)
    if kind in csv_stale or not os.path.isfile(path) or os.path.getsize(path) == 0:
        write_csv(name, cols, [fn(r) for r in store[kind]])
        csv_stale.discard(kind)
        return
    try:
        with open(path, "a", newline="") as f:
            csv.writer(f).writerows([fn(r) for r in rows])
    except Exception:
        csv_stale.add(kind)
        raise


def load_store():
    try:
        _load_store()
        rewrite_csvs()
    except Exception:
        log("load_store failed (continuing without old data):\n" + traceback.format_exc())


def _load_store():
    os.makedirs(DATA, exist_ok=True)
    for kind, fn in (("sig", "signals.jsonl"), ("fin", "final_calls.jsonl"), ("sim", "sim_trades.jsonl")):
        path = os.path.join(DATA, fn)
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    store[kind].append(r)
                    seen[kind].add(rkey(r))
    path = os.path.join(DATA, "calibration.csv")
    if os.path.isfile(path):
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            rd = csv.reader(f)
            next(rd, None)
            for row in rd:
                try:
                    r = {"w": int(row[0]) or None, "s": row[1], "t": int(row[2]) or None, "x": float(row[3]), "y": int(row[4])}
                except Exception:
                    continue
                CAL_COUNT[0] += 1
                cal_recent.append(r)
                k = cal_key(r)
                cal_seen.append(k)
                cal_seen_set.add(k)


PRICE_HEADER = ("t,coin,px,cb,kr,okx,hl,okx_bid,okx_ask,okx_bidsz,okx_asksz,cb_bid,cb_ask,cb_bidsz,cb_asksz,"
                "k_yes_bid,k_yes_ask,k_no_bid,k_no_ask,k_strike,k_close")
PRICE_KEEP_DAYS = 14


def save_prices(body):
    """Per-second price research log (data/prices-YYYYMMDD.csv.gz, one file per UTC day, rows appended as gzip members so the file
    stays valid at all times and small): the combined price, each exchange's own price, top-of-book sizes and Kalshi's quote.
    Nothing in the app reads it; it exists so alternative models can be tested later on exactly what the page saw."""
    rows = [str(r) for r in (body.get("rows") or []) if isinstance(r, str) and 10 < len(r) < 400]
    if not rows:
        return {"ok": True, "rows": 0}
    by_day = {}
    for r in rows:
        try:
            day = time.strftime("%Y%m%d", time.gmtime(int(r.split(",", 1)[0])))
        except Exception:
            continue
        by_day.setdefault(day, []).append(r)
    with lock:
        os.makedirs(DATA, exist_ok=True)
        for day, rs in by_day.items():
            path = os.path.join(DATA, "prices-%s.csv.gz" % day)
            text = ("" if os.path.exists(path) else PRICE_HEADER + "\n") + "\n".join(rs) + "\n"
            with open(path, "ab") as f:
                f.write(gzip.compress(text.encode("utf-8"), 6))
        try:      # keep two weeks
            cutoff = time.strftime("%Y%m%d", time.gmtime(time.time() - PRICE_KEEP_DAYS * 86400))
            for fn in os.listdir(DATA):
                if fn.startswith("prices-") and fn.endswith(".csv.gz") and fn[7:15] < cutoff:
                    os.remove(os.path.join(DATA, fn))
        except Exception:
            pass
    return {"ok": True, "rows": len(rows)}


def save_data(body):
    added = {"sig": 0, "fin": 0, "cal": 0, "sim": 0}
    with lock:
        os.makedirs(DATA, exist_ok=True)
        fresh = {"sig": [], "fin": [], "sim": []}
        for kind, fn in (("sig", "signals.jsonl"), ("fin", "final_calls.jsonl"), ("sim", "sim_trades.jsonl")):
            with open(os.path.join(DATA, fn), "a", encoding="utf-8") as f:
                for r in body.get(kind) or []:
                    k = rkey(r)
                    if k in seen[kind]:
                        continue
                    seen[kind].add(k)
                    store[kind].append(r)
                    fresh[kind].append(r)
                    f.write(json.dumps(r, separators=(",", ":")) + "\n")
                    added[kind] += 1
        newcal = []
        for r in body.get("cal") or []:
            k = cal_key(r)
            if k in cal_seen_set:
                continue
            if len(cal_seen) == cal_seen.maxlen:
                cal_seen_set.discard(cal_seen[0])
            cal_seen.append(k)
            cal_seen_set.add(k)
            cal_recent.append(r)
            newcal.append(r)
            added["cal"] += 1
        if newcal:
            path = os.path.join(DATA, "calibration.csv")
            new_file = not os.path.isfile(path)
            with open(path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(CAL_COLS)
                for r in newcal:
                    w.writerow([r.get("w") or 0, r.get("s") or "", r.get("t") or 0, r.get("x"), r.get("y")])
            CAL_COUNT[0] += len(newcal)
        for kind in ("sig", "fin", "sim"):
            if added[kind]:
                append_csv(kind, fresh[kind])
        if isinstance(body.get("simstate"), dict):
            tmp = os.path.join(DATA, "sim_state.json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(body["simstate"], f, indent=1)
            os.replace(tmp, os.path.join(DATA, "sim_state.json"))
        if body.get("summary"):
            s = dict(body["summary"])
            s["saved_at_utc"] = iso(time.time())
            with open(os.path.join(DATA, "calibration_summary.json"), "w") as f:
                json.dump(s, f, indent=2)
        totals = {"signals": len(store["sig"]), "final_calls": len(store["fin"]), "calibration_samples": CAL_COUNT[0], "sim_trades": len(store["sim"])}
    return {"ok": True, "added": added, "totals": totals}

if sys.stdout is None:      # started with pythonw (no console window)
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


# --------------------------------------------------------------------------- server
def find_dashboard():
    for base in (HERE, BUNDLE):
        for name in ("kalshi_dashboard_v4.html", "kalshi_dashboard.html"):
            p = os.path.join(base, name)
            if os.path.isfile(p):
                return p
    for name in sorted(os.listdir(HERE)) if os.path.isdir(HERE) else []:
        if name.lower().endswith(".html") and "kalshi" in name.lower():
            return os.path.join(HERE, name)
    return None


_CTX = []


def ssl_ctx():
    """One shared certificate store for the whole run (building it from disk on every request was the slowest part of a fetch)."""
    if not _CTX:
        _CTX.append(ssl.create_default_context())
    return _CTX[0]


def _pool_wanted():
    """Keep-alive connections go straight to Kalshi; on a network that needs a proxy, use the normal route instead."""
    try:
        px = urllib.request.getproxies()
        if px.get("https") or px.get("all"):
            return bool(urllib.request.proxy_bypass(urllib.parse.urlsplit(UPSTREAM).hostname or ""))
    except Exception:
        pass
    return True


POOL_ON = [_pool_wanted()]
POOL_WORKED = [False]
_idle = []                       # idle keep-alive connections to Kalshi, reused so each request skips the TCP + TLS handshake
_idle_lock = threading.Lock()
POOL_MAX, POOL_IDLE = 8, 20.0


def _pooled_get(url):
    u = urllib.parse.urlsplit(url)
    path = u.path + ("?" + u.query if u.query else "")
    for attempt in (0, 1):
        c = None
        if attempt == 0:
            with _idle_lock:
                while _idle:
                    host, cc, t = _idle.pop()
                    if host == u.netloc and time.time() - t < POOL_IDLE:
                        c = cc
                        break
                    cc.close()
        fresh = c is None
        if fresh:
            c = http.client.HTTPSConnection(u.netloc, timeout=8, context=ssl_ctx())
        try:
            c.request("GET", path, headers={"User-Agent": "kalshi-helper/1.0", "Accept": "application/json"})
            r = c.getresponse()
            body = r.read()
        except Exception:
            c.close()
            if fresh:
                raise
            continue                 # the server had closed an idle connection: try once more on a new one
        if 300 <= r.status < 400:
            c.close()
            raise RuntimeError("redirect")     # let the normal route follow it
        if r.will_close:
            c.close()
        else:
            with _idle_lock:
                if len(_idle) < POOL_MAX:
                    _idle.append((u.netloc, c, time.time()))
                else:
                    c.close()
        if r.status >= 400 and not body:
            body = json.dumps({"error": "Kalshi returned HTTP %d" % r.status}).encode()
        POOL_WORKED[0] = True
        return r.status, body
    raise RuntimeError("no connection")


def fetch_upstream(url):
    """Reused connection first; if that is not possible, the normal fetch; and if this Python can't verify certificates (common on Mac), curl."""
    if POOL_ON[0]:
        try:
            return _pooled_get(url)
        except Exception:
            if not POOL_WORKED[0]:
                POOL_ON[0] = False   # never worked on this computer (proxy, certificates...): stop trying it
    req = urllib.request.Request(url, headers={"User-Agent": "kalshi-helper/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8, context=ssl_ctx()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or json.dumps({"error": "Kalshi returned HTTP %d" % e.code}).encode()
    except Exception as e:
        msg = str(e)
        try:   # curl ships with macOS, Windows 10+ and most Linux and uses the system certificates
            p = subprocess.run(["curl", "-sS", "--max-time", "8", "-H", "Accept: application/json", url],
                               capture_output=True, timeout=12)
            if p.returncode == 0 and p.stdout:
                return 200, p.stdout
            msg += " | curl: " + (p.stderr.decode("utf-8", "ignore").strip() or "no response")
        except Exception as e2:
            msg += " | curl unavailable: %s" % e2
        return 502, json.dumps({"error": msg}).encode()


# --------------------------------------------------------------------------- Kalshi account (read-only)
# Your private key stays in the "keys" folder next to this file. It is read here, in this program, to sign requests, and it is
# never sent to the dashboard page or anywhere else. The only requests that are ever signed are the three GET calls in
# ACCT_PATHS (balance, positions, fills): nothing in this file can place, change or cancel an order.
KEYS_DIR = os.path.join(HERE, "keys")
ACCT_PATHS = ("/portfolio/balance", "/portfolio/positions", "/portfolio/fills", "/portfolio/settlements")
DEMO_BASE = "https://external-api.demo.kalshi.co/trade-api/v2"
PROD_BASES = [UPSTREAM, "https://external-api.kalshi.com/trade-api/v2"]
KEY_EXT = (".pem", ".key", ".txt", ".p8")
_key_cache = {}
acct_cache = {"t": 0.0, "env": None, "data": None}
acct_lock = threading.Lock()


# ---- tiny DER reader (just enough to open PEM private keys)
def _der(b, i=0):
    tag, ln = b[i], b[i + 1]
    i += 2
    if ln & 0x80:
        k = ln & 0x7F
        ln = int.from_bytes(b[i:i + k], "big")
        i += k
    return tag, b[i:i + ln], i + ln


def _der_items(b):
    out, i = [], 0
    while i < len(b):
        t, c, i = _der(b, i)
        out.append((t, c))
    return out


def parse_private_key(text):
    """PEM text -> ("ed25519", 32-byte seed) or ("rsa", (n, e, d, p, q, dp, dq, qinv)). Raises ValueError with a plain-English reason."""
    import base64
    m = re.search(r"-----BEGIN ([A-Z0-9 ]*PRIVATE KEY)-----(.+?)-----END [A-Z0-9 ]*PRIVATE KEY-----", text, re.S)
    if not m:
        raise ValueError("That file doesn't contain a private key (it should start with -----BEGIN ... PRIVATE KEY-----).")
    label, body = m.group(1), m.group(2)
    if "ENCRYPTED" in label or "Proc-Type" in body:
        raise ValueError("That private key is password-protected, which isn't supported. Use the key file exactly as Kalshi gave it to you.")
    try:
        der = base64.b64decode("".join(body.split()))
        top = _der_items(_der(der)[1])
        if label == "RSA PRIVATE KEY":                                  # PKCS#1
            nums = [int.from_bytes(c, "big") for t, c in top[1:9]]
            return "rsa", tuple(nums)
        algid = _der_items(top[1][1])
        oid = algid[0][1]
        inner = top[2][1]
        if oid == bytes.fromhex("2b6570"):                              # Ed25519
            seed = _der(inner)[1]
            if len(seed) != 32:
                raise ValueError("bad length")
            return "ed25519", seed
        if oid == bytes.fromhex("2a864886f70d010101"):                  # RSA in PKCS#8
            nums = [int.from_bytes(c, "big") for t, c in _der_items(_der(inner)[1])[1:9]]
            return "rsa", tuple(nums)
    except ValueError:
        raise
    except Exception:
        raise ValueError("That private key file couldn't be read. Make sure it's the whole file Kalshi gave you, unedited.")
    raise ValueError("That kind of key isn't supported. Create an Ed25519 or RSA key on Kalshi.")


# ---- Ed25519 (RFC 8032), pure Python
_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _ed_add(a, b):
    A, B = (a[1] - a[0]) * (b[1] - b[0]) % _P, (a[1] + a[0]) * (b[1] + b[0]) % _P
    C, D = 2 * a[3] * b[3] * _D % _P, 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _ed_mul(s, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _ed_add(q, pt)
        pt = _ed_add(pt, pt)
        s >>= 1
    return q


def _ed_enc(pt):
    zi = pow(pt[2], _P - 2, _P)
    x, y = pt[0] * zi % _P, pt[1] * zi % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _ed_base():
    y = 4 * pow(5, _P - 2, _P) % _P
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if x & 1:
        x = _P - x
    return (x, y, 1, x * y % _P)


_ED_G = _ed_base()


def ed25519_sign(seed, msg):
    h = hashlib.sha512(seed).digest()
    a = (int.from_bytes(h[:32], "little") & ((1 << 254) - 8)) | (1 << 254)
    A = _ed_enc(_ed_mul(a, _ED_G))
    r = int.from_bytes(hashlib.sha512(h[32:] + msg).digest(), "little") % _Q
    R = _ed_enc(_ed_mul(r, _ED_G))
    k = int.from_bytes(hashlib.sha512(R + A + msg).digest(), "little") % _Q
    return R + ((r + k * a) % _Q).to_bytes(32, "little")


# ---- RSA-PSS, SHA-256, MGF1(SHA-256), salt length 32 (what Kalshi asks for RSA keys)
def _mgf1(seed, n):
    out, c = b"", 0
    while len(out) < n:
        out += hashlib.sha256(seed + c.to_bytes(4, "big")).digest()
        c += 1
    return out[:n]


def rsa_pss_sign(key, msg):
    n, e, d, p, q, dp, dq, qi = key
    bits = n.bit_length() - 1
    em_len = (bits + 7) // 8
    h_len = 32
    m_hash = hashlib.sha256(msg).digest()
    salt = os.urandom(h_len)
    H = hashlib.sha256(b"\0" * 8 + m_hash + salt).digest()
    db = b"\0" * (em_len - h_len * 2 - 2) + b"\x01" + salt
    masked = bytearray(x ^ y for x, y in zip(db, _mgf1(H, em_len - h_len - 1)))
    masked[0] &= 0xFF >> (8 * em_len - bits)
    m = int.from_bytes(bytes(masked) + H + b"\xbc", "big")
    s1, s2 = pow(m % p, dp, p), pow(m % q, dq, q)       # CRT
    s = s2 + q * (qi * (s1 - s2) % p)
    return s.to_bytes((n.bit_length() + 7) // 8, "big")


def sign_message(key, msg):
    kind, k = key
    return ed25519_sign(k, msg) if kind == "ed25519" else rsa_pss_sign(k, msg)


# ---- finding the key and the settings
def find_key_file():
    try:
        files = [os.path.join(KEYS_DIR, f) for f in os.listdir(KEYS_DIR)
                 if f.lower().endswith(KEY_EXT) and os.path.isfile(os.path.join(KEYS_DIR, f))]
    except OSError:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for p in files:
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                if "PRIVATE KEY-----" in f.read(20000):
                    return p
        except OSError:
            pass
    return None


def load_key():
    """(path, key) for the newest private key file in the keys folder. Raises ValueError with a plain reason."""
    p = find_key_file()
    if not p:
        raise ValueError("No private key file found yet. Put the key file Kalshi gave you into the keys folder.")
    sig = (p, os.path.getmtime(p))
    hit = _key_cache.get("k")
    if hit and hit[0] == sig:
        return p, hit[1]
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        key = parse_private_key(f.read())
    _key_cache["k"] = (sig, key)
    return p, key


def acct_config():
    cfg = load_settings()
    env = "demo" if cfg.get("kalshi_env") == "demo" else "prod"
    return (cfg.get("kalshi_key_id") or "").strip(), env


def mask_id(s):
    return (s[:4] + "…" + s[-4:]) if len(s) > 10 else ("…" if s else "")


def acct_status():
    key_id, env = acct_config()
    out = {"key_id": mask_id(key_id), "has_id": bool(key_id), "env": env, "keys_dir": KEYS_DIR,
           "has_key": False, "key_type": None, "key_error": None}
    try:
        p, key = load_key()
        out["has_key"] = True
        out["key_type"] = key[0]
        out["key_file"] = os.path.basename(p)
    except ValueError as e:
        out["key_error"] = str(e) if find_key_file() else None
    out["ready"] = out["has_id"] and out["has_key"]
    return out


# ---- signed GET (only the three whitelisted paths)
def signed_get(base, path, query=""):
    if path not in ACCT_PATHS:
        raise ValueError("not allowed")
    key_id, _env = acct_config()
    _p, key = load_key()
    u = urllib.parse.urlsplit(base)
    full_path = u.path.rstrip("/") + path                         # this exact path, without the query, is what gets signed
    ts = str(int(time.time() * 1000))
    import base64
    sig = base64.b64encode(sign_message(key, (ts + "GET" + full_path).encode())).decode()
    headers = {"KALSHI-ACCESS-KEY": key_id, "KALSHI-ACCESS-TIMESTAMP": ts, "KALSHI-ACCESS-SIGNATURE": sig,
               "Accept": "application/json", "User-Agent": "kalshi-helper/1.0"}
    url = u.scheme + "://" + u.netloc + full_path + (("?" + query) if query else "")
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b"{}"
    except Exception as e:
        try:
            args = ["curl", "-sS", "--max-time", "10", "-w", "\n%{http_code}"]
            for k, v in headers.items():
                args += ["-H", "%s: %s" % (k, v)]
            pr = subprocess.run(args + [url], capture_output=True, timeout=14)
            if pr.returncode == 0 and pr.stdout:
                body, _, code = pr.stdout.rpartition(b"\n")
                return int(code or 0), body
        except Exception:
            pass
        raise ConnectionError(str(e))


def _bases(env):
    return [DEMO_BASE] if env == "demo" else PROD_BASES


def acct_get(path, query=""):
    key_id, env = acct_config()
    last = None
    for base in _bases(env):
        try:
            st, body = signed_get(base, path, query)
        except ConnectionError as e:
            last = e
            continue                                               # can't reach this address: try the next one
        try:
            data = json.loads(body.decode("utf-8", "ignore") or "{}")
        except ValueError:
            data = {}
        return st, data
    raise ConnectionError(str(last) if last else "no connection")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _usd(o, dollars_key, cents_key):
    """Kalshi sends money as dollar strings ("0.5600"); older replies used whole cents. Returns dollars."""
    v = _f(o.get(dollars_key))
    if v is not None:
        return v
    v = _f(o.get(cents_key))
    return None if v is None else v / 100.0


def norm_summary(bal, pos, fills):
    cash = _usd(bal, "balance_dollars", "balance")
    if cash is not None:      # Kalshi can hold fractions of a cent (fee rebates) but shows whole cents: round down so we never claim a cent more than it does
        cash = math.floor(cash * 100 + 1e-6) / 100.0
    out = {"balance": cash,
           "portfolio_value": _usd(bal, "portfolio_value_dollars", "portfolio_value"),
           "positions": [], "fills": []}
    for r in (pos.get("market_positions") or []):
        n = _f(r.get("position_fp"))
        if n is None:
            n = _f(r.get("position"))
        if not n:
            continue
        out["positions"].append({"ticker": r.get("ticker"), "side": "YES" if n > 0 else "NO", "contracts": abs(n),
                                 "cost": _usd(r, "market_exposure_dollars", "market_exposure"),
                                 "pnl": _usd(r, "realized_pnl_dollars", "realized_pnl"),
                                 "fees": _usd(r, "fees_paid_dollars", "fees_paid")})
    for r in (fills.get("fills") or []):
        side = (r.get("outcome_side") or r.get("side") or "").upper()
        py = _usd(r, "yes_price_dollars", "yes_price")
        pn = _usd(r, "no_price_dollars", "no_price")
        cnt = _f(r.get("count_fp"))
        if cnt is None:
            cnt = _f(r.get("count"))
        fee = _f(r.get("fee_cost"))
        out["fills"].append({"time": r.get("created_time") or r.get("ts"), "ticker": r.get("ticker") or r.get("market_ticker"),
                             "side": side, "action": (r.get("action") or "buy").upper(), "contracts": cnt,
                             "price": pn if side == "NO" else py, "fee": fee, "taker": bool(r.get("is_taker"))})
    out["fills"].sort(key=lambda x: str(x["time"] or ""), reverse=True)
    out["positions"].sort(key=lambda x: str(x["ticker"] or ""))
    return out


def acct_error_text(st, data):
    if st in (401, 403):
        return ("Kalshi didn't accept the key (HTTP %d). Check that the Key ID is the one that belongs to the private key file, "
                "that the environment (real or demo) is right, and that this computer's clock is correct." % st)
    msg = ""
    if isinstance(data, dict):
        msg = str(data.get("message") or data.get("error") or "")
        if data.get("details"):
            msg += " (%s)" % str(data["details"])[:100]
        if isinstance(data.get("error"), dict):
            msg = str(data["error"].get("message") or data["error"].get("code") or "")
    return "Kalshi returned HTTP %d%s" % (st, (": " + msg[:160]) if msg else "")


def acct_summary(force=False):
    s = acct_status()
    if not s["ready"]:
        return {"ok": False, "status": s, "error": s["key_error"] or ("Add your Key ID" if not s["has_id"] else "Add your private key file")}
    with acct_lock:
        c = acct_cache
        if not force and c["data"] and c["env"] == s["env"] and time.time() - c["t"] < 5:
            return c["data"]
    try:
        res = {}
        errs = []

        def run(name, path, query):
            try:
                res[name] = acct_get(path, query)
            except Exception as e:
                errs.append(str(e))
        th = [threading.Thread(target=run, args=a) for a in (("bal", "/portfolio/balance", ""),
                                                             ("pos", "/portfolio/positions", "limit=200&count_filter=position"),
                                                             ("fil", "/portfolio/fills", "limit=100"))]
        for t in th:
            t.start()
        for t in th:
            t.join(15)
        if errs or len(res) < 3:
            out = {"ok": False, "status": s, "error": "Couldn't reach Kalshi: " + (errs[0] if errs else "timed out")}
        else:
            bad = [(st, d) for st, d in res.values() if st >= 400]
            if bad:
                out = {"ok": False, "status": s, "error": acct_error_text(bad[0][0], bad[0][1])}
            else:
                out = {"ok": True, "status": s, "t": time.time(), **norm_summary(res["bal"][1], res["pos"][1], res["fil"][1])}
    except Exception as e:
        log("account summary failed:\n" + traceback.format_exc())
        out = {"ok": False, "status": s, "error": str(e)}
    with acct_lock:
        acct_cache.update(t=time.time(), env=s["env"], data=out)
        if out.get("ok") and out.get("balance") is not None:
            bal_cache.update(t=time.time(), env=s["env"], v=out["balance"])
    return out


bal_cache = {"t": 0.0, "env": None, "v": None}


def cash_balance(max_age=15.0):
    """The Kalshi cash balance for allocation checks. A recent reading is reused, and a failed read is retried, so setting many
    allocations in a row doesn't hit Kalshi's rate limit."""
    env = acct_config()[1]
    if bal_cache["v"] is not None and bal_cache["env"] == env and time.time() - bal_cache["t"] < max_age:
        return bal_cache["v"]
    last = ""
    for i in range(3):
        sm = acct_summary(True)
        if sm.get("ok") and sm.get("balance") is not None:
            return sm["balance"]
        last = sm.get("error") or ""
        time.sleep(1.2 * (i + 1))
    raise ValueError("Couldn't read your Kalshi balance, so nothing was changed." + (" (" + last + ")" if last else ""))


# ---- placing bets (guarded)
# Every rule below is enforced here, in the helper, not just in the page: the page cannot talk it out of them.
#   * trading is OFF until you switch it on in the Kalshi account panel (and it switches itself off again if you change environment)
#   * only 15-minute crypto markets (KX...15M) can be bought; only "buy", never sell
#   * a mode can only bet its own allocated money; a hand-placed bet can only use cash no mode has allocated
#   * every order is a fill-or-kill limit order: it fills completely at your price or better, or not at all
#   * every attempt, accepted or refused, is written to data/live_orders.jsonl
TICKER_RE = re.compile(r"^KX[A-Z0-9]+15M-[A-Z0-9\-]+$")
LIVE_LOG = "live_orders.jsonl"
DEF_MAX_BET, DEF_DAILY = 5.0, 25.0
_last_order = [0.0]
order_lock = threading.Lock()


class TradeError(Exception):
    pass


def trade_cfg():
    cfg = load_settings()
    def num(k, d):
        try:
            v = float(cfg.get(k))
            return v if v > 0 else d
        except (TypeError, ValueError):
            return d
    return {"trading": bool(cfg.get("kalshi_trading")), "max_bet": num("kalshi_max_bet", DEF_MAX_BET), "daily": num("kalshi_daily", DEF_DAILY)}


def live_rows():
    p = os.path.join(DATA, LIVE_LOG)
    out = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            for ln in f:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def live_append(row):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, LIVE_LOG), "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def spent_today(env):
    day = time.strftime("%Y-%m-%d")
    return sum(r.get("cost_total") or 0 for r in live_rows() if r.get("day") == day and r.get("env") == env and r.get("filled"))


# Kalshi's order format takes contract counts with up to 2 decimals. Auto and Timed orders use it to spend the whole budget instead of rounding
# down to whole contracts. If Kalshi ever refuses a fractional count (a clear 400/422 saying so), that order is re-sent as whole contracts and
# fractions stay off until the helper restarts. Anything unclear (a timeout, a fill-or-kill kill) is never re-sent.
FRAC = {"ok": True}
FRAC_ERR = re.compile(r"fraction|decimal|whole|integer|increment|granular|precision|multiple|count", re.I)


def est_fee(count, price_cents):
    p = price_cents / 100.0
    return math.ceil(0.07 * count * p * (1 - p) * 100 - 1e-9) / 100.0          # Kalshi's taker fee formula, rounded up to the cent


# ---- results from Kalshi and real bankrolls
# Each mode gets a real bankroll you set (the "Start $"). It can only ever bet that amount plus what it has won or lost since,
# so the rest of your account is untouched. This is enforced here, in the helper, using Kalshi's own market results.
RESULTS_FILE = "live_results.json"
_res = {"d": None, "busy": False, "last": 0.0}


def _res_cache():
    if _res["d"] is None:
        try:
            with open(os.path.join(DATA, RESULTS_FILE), "r", encoding="utf-8") as f:
                _res["d"] = json.load(f)
        except Exception:
            _res["d"] = {}
    return _res["d"]


def _resolve_worker(todo):
    try:
        d = _res_cache()
        changed = False
        for env, tk in todo[:6]:
            try:
                st, body = fetch_upstream((DEMO_BASE if env == "demo" else UPSTREAM) + "/markets/" + urllib.parse.quote(tk))
                m = json.loads(body.decode("utf-8", "ignore") or "{}").get("market") or {}
                if st < 400 and m.get("result") in ("yes", "no"):
                    d[env + "|" + tk] = m["result"]
                    changed = True
            except Exception:
                pass
        if changed:
            os.makedirs(DATA, exist_ok=True)
            with open(os.path.join(DATA, RESULTS_FILE), "w", encoding="utf-8") as f:
                json.dump(d, f)
    finally:
        _res["busy"] = False


ACTUALS_FILE = "live_actuals.json"
_act = {"d": None, "busy": False, "last": 0.0, "tries": {}}


def _act_cache():
    if _act["d"] is None:
        try:
            with open(os.path.join(DATA, ACTUALS_FILE), "r", encoding="utf-8") as f:
                _act["d"] = json.load(f)
        except Exception:
            _act["d"] = {}
    return _act["d"]


def _fill_price(r, side):
    py, pn = _usd(r, "yes_price_dollars", "yes_price"), _usd(r, "no_price_dollars", "no_price")
    p = py if side == "yes" else pn
    if p is None:
        p = (1 - pn if side == "yes" else 1 - py) if (pn if side == "yes" else py) is not None else None
    return p


def _actuals_worker(fills, settles):
    """Replaces our own estimates with what Kalshi actually recorded: the fills (price and fee per contract) and, once a market has
    settled, the payout. Anything Kalshi doesn't return in a form we can read is left as the estimate."""
    try:
        d = _act_cache()
        changed = False
        for oid, ticker, side in fills[:4]:
            try:
                st, data = acct_get("/portfolio/fills", "order_id=%s&limit=100" % urllib.parse.quote(str(oid)))
                cnt = cost = fee = 0.0
                if st < 400:
                    for r in (data.get("fills") or []):
                        if r.get("order_id") not in (None, oid):
                            continue
                        c = _f(r.get("count_fp"))
                        c = _f(r.get("count")) if c is None else c
                        p = _fill_price(r, side)
                        if not c or p is None:
                            continue
                        cnt += c
                        cost += c * p
                        fee += _f(r.get("fee_cost")) or 0.0
                if cnt > 0:
                    d["f|" + str(oid)] = {"count": cnt, "cost": round(cost, 4), "fees": round(fee, 4)}
                    changed = True
            except Exception:
                pass
        for env, ticker in settles[:4]:
            try:
                st, data = acct_get("/portfolio/settlements", "ticker=%s&limit=20" % urllib.parse.quote(ticker))
                if st < 400:
                    for r in (data.get("settlements") or []):
                        if (r.get("ticker") or r.get("market_ticker")) != ticker:
                            continue
                        rev = _usd(r, "revenue_dollars", "revenue")
                        if rev is not None:
                            d["s|%s|%s" % (env, ticker)] = {"payout": round(rev, 4)}
                            changed = True
                            break
            except Exception:
                pass
        if changed:
            os.makedirs(DATA, exist_ok=True)
            with open(os.path.join(DATA, ACTUALS_FILE), "w", encoding="utf-8") as f:
                json.dump(d, f)
    finally:
        _act["busy"] = False


def annotate(rows):
    """Adds Kalshi's result ("yes"/"no") to each filled row once its market has settled, then replaces our estimates with Kalshi's own
    numbers (price and fees actually paid, payout) as they become available. Missing ones are fetched in the background."""
    d, a, now, todo, tf, ts = _res_cache(), _act_cache(), time.time(), [], [], []
    for r in rows:
        r["res"] = d.get("%s|%s" % (r.get("env"), r.get("ticker"))) if r.get("filled") else None
        if r.get("filled") and not r["res"] and now > (r.get("w") or (r.get("t") or now) + 900) + 15:
            k = (r.get("env"), r.get("ticker"))
            if k not in todo:
                todo.append(k)
        if not r.get("filled"):
            continue
        oid = r.get("order_id")
        f = a.get("f|" + str(oid)) if oid else None
        if f:
            r["fill_count"] = f["count"]
            r["cost"] = f["cost"]
            r["fees"] = f["fees"]
            r["cost_total"] = round(f["cost"] + f["fees"], 4)
            r["actual"] = True
        elif oid and now - (r.get("t") or now) > 2 and _act["tries"].get(("f", oid), 0) < 6:
            tf.append((oid, r.get("ticker"), r.get("side")))
        fc, ct = r.get("fill_count") or 0, r.get("cost_total") or 0
        if fc and ct:
            r["avg_cents"] = round((r.get("cost") or ct) / fc * 100, 1)
            r["mult"] = round(fc / ct, 3)               # what each $1 paid (fees included) pays back if it wins
        if r["res"]:
            # Kalshi pays $1 per winning contract. Only this order's own contracts count: the settlement Kalshi reports covers the
            # whole position in the market, which also holds any contracts bought by hand or by another order.
            won = r["res"] == r.get("side")
            r["payout"] = fc if won else 0.0
            r["payout_actual"] = False
    if todo and not _res["busy"] and now - _res["last"] > 6:
        _res["busy"], _res["last"] = True, now
        threading.Thread(target=_resolve_worker, args=(todo,), daemon=True).start()
    if (tf or ts) and not _act["busy"] and now - _act["last"] > 8:
        _act["busy"], _act["last"] = True, now
        for oid, _t, _s in tf[:4]:
            _act["tries"][("f", oid)] = _act["tries"].get(("f", oid), 0) + 1
        for _e, tk in ts[:4]:
            _act["tries"][("s", tk)] = _act["tries"].get(("s", tk), 0) + 1
        threading.Thread(target=_actuals_worker, args=(tf, ts), daemon=True).start()
    return rows


def sym_of(ticker):
    m = re.match(r"^KX([A-Z0-9]+?)15M-", ticker or "")
    return m.group(1) if m else ""


def budget_stats(env, rows=None):
    cfg = (load_settings().get("kalshi_budget") or {}).get(env) or {}
    rows = rows if rows is not None else annotate(live_rows())
    out = {}
    for src, keys in cfg.items():
        out[src] = {}
        for key, b in keys.items():
            start, since = float(b.get("start") or 0), float(b.get("since") or 0)
            mine = [r for r in rows if r.get("filled") and r.get("env") == env and r.get("src") == src and (r.get("t") or 0) >= since - 0.001
                    and (src != "sim" or sym_of(r.get("ticker")) == key)]
            net, peak, w, l = 0.0, max(start, 0.0), 0, 0
            for r in sorted([r for r in mine if r.get("res")], key=lambda r: (r.get("w") or r.get("t") or 0)):
                won = r["res"] == r.get("side")
                net += (r.get("payout") or 0) - (r.get("cost_total") or 0)
                w, l = w + (1 if won else 0), l + (0 if won else 1)
                peak = max(peak, start + net)
            opn = [r for r in mine if not r.get("res")]
            oc = sum(r.get("cost_total") or 0 for r in opn)
            out[src][key] = {"start": start, "since": since, "n": len(mine), "w": w, "l": l, "net": round(net, 4), "peak": round(peak, 4),
                             "bank": round(start + net, 4), "open": round(oc, 4), "open_n": len(opn), "avail": round(start + net - oc, 4)}
    return out


def budget_set(body):
    """Set how much real money a mode/coin has allocated. The number is the bankroll itself (what it was given plus what it has won
    or lost), so raising it deposits more from cash and lowering it sends the difference back to cash. 0 releases it entirely."""
    _kid, env = acct_config()
    src, key = body.get("src"), str(body.get("key") or "*")
    if src not in ("auto", "sim"):
        raise ValueError("Unknown mode.")
    if src == "auto":
        key = "*"
    elif not re.match(r"^[A-Z0-9]{2,12}$", key):
        raise ValueError("Unknown coin.")
    target = float(body.get("alloc", body.get("start")))
    if not (0 <= target <= 1000000):
        raise ValueError("That amount isn't valid.")
    target = round(target, 2)
    cfg = load_settings()
    bud = cfg.setdefault("kalshi_budget", {}).setdefault(env, {})
    cur = budget_stats(env).get(src, {}).get(key)
    if cur and cur["open"] > 0 and target < cur["open"] - 1e-9:
        raise ValueError("$%.2f of it is in a bet that hasn't settled yet, so it can't go below that until the bet finishes." % cur["open"])
    if target > 0:
        sm = {"balance": cash_balance()}
        others = sum(v["avail"] for sn, ks in budget_stats(env).items() for kn, v in ks.items() if not (sn == src and kn == key))
        mine = target - (cur["open"] if cur else 0.0)           # what this one will have free to bet
        if others + mine > sm["balance"] + 1e-9:
            raise ValueError("You have $%.2f in cash and $%.2f is already allocated to other modes, so only $%.2f more can be allocated here."
                             % (sm["balance"], max(others, 0), max(sm["balance"] - others, 0)))
        if cur:      # keep the record (wins, losses, net); only move the capital so that bankroll == target
            bud[src][key]["start"] = round(target - cur["net"], 4)
        else:
            bud.setdefault(src, {})[key] = {"start": target, "since": time.time()}
    else:
        bud.get(src, {}).pop(key, None)
    save_settings(cfg)
    acct_cache["data"] = None
    return budget_stats(env)


def budget_set_many(items):
    """Set several allocations at once (for example Timed bets split evenly across coins): one balance reading, everything checked
    first, then all applied together, so it either all happens or none of it does."""
    _kid, env = acct_config()
    if not isinstance(items, list) or not items or len(items) > 40:
        raise ValueError("Nothing to set.")
    plan = {}
    sweeps = set()
    for it in items:
        src, key = it.get("src"), str(it.get("key") or "*")
        if src not in ("auto", "sim"):
            raise ValueError("Unknown mode.")
        if src == "auto":
            key = "*"
        elif not re.match(r"^[A-Z0-9]{2,12}$", key):
            raise ValueError("Unknown coin.")
        if it.get("sweep"):
            sweeps.add((src, key))
            continue
        t = round(float(it.get("alloc")), 2)
        if not (0 <= t <= 1000000):
            raise ValueError("That amount isn't valid.")
        plan[(src, key)] = t
    stats = budget_stats(env)
    for (src, key), t in plan.items():
        cur = stats.get(src, {}).get(key)
        if cur and cur["open"] > 0 and t < cur["open"] - 1e-9:
            raise ValueError("%s: $%.2f of it is in a bet that hasn't settled yet, so it can't go below that until the bet finishes." % (key if src == "sim" else "Auto", cur["open"]))
    total = 0.0
    for sn, ks in stats.items():
        for kn, v in ks.items():
            if (sn, kn) in plan:
                total += max(plan[(sn, kn)] - v["open"], 0.0)
            else:
                total += max(v["avail"], 0.0)
    total += sum(t for (sn, kn), t in plan.items() if kn not in stats.get(sn, {}))
    if total > 1e-9 and any(t > 0 for t in plan.values()):
        bal = cash_balance()
        if total > bal + 1e-9:
            raise ValueError("That would put $%.2f to work, but you only have $%.2f in cash." % (total, bal))
    cfg = load_settings()
    bud = cfg.setdefault("kalshi_budget", {}).setdefault(env, {})
    for (src, key), t in plan.items():
        cur = stats.get(src, {}).get(key)
        if t > 0:
            if cur:
                bud[src][key]["start"] = round(t - cur["net"], 4)
            else:
                bud.setdefault(src, {})[key] = {"start": t, "since": time.time()}
        else:
            bud.get(src, {}).pop(key, None)
    for (src, key) in sweeps:      # leftover too small to bet: bank goes to exactly $0 (the wins/losses record stays) and the money is back in cash
        cur = stats.get(src, {}).get(key)
        if cur and cur["open"] <= 1e-9 and cur["bank"] < 1.0:
            bud[src][key]["start"] = round(-cur["net"], 4)
    save_settings(cfg)
    acct_cache["data"] = None
    return budget_stats(env)


def signed_post(base, path, body):
    if path != "/portfolio/events/orders":          # the only thing this program is allowed to POST: Kalshi's V2 create-order endpoint
        raise ValueError("not allowed")
    import base64
    key_id, _env = acct_config()
    _p, key = load_key()
    u = urllib.parse.urlsplit(base)
    full_path = u.path.rstrip("/") + path
    ts = str(int(time.time() * 1000))
    sig = base64.b64encode(sign_message(key, (ts + "POST" + full_path).encode())).decode()
    headers = {"KALSHI-ACCESS-KEY": key_id, "KALSHI-ACCESS-TIMESTAMP": ts, "KALSHI-ACCESS-SIGNATURE": sig,
               "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "kalshi-helper/1.0"}
    req = urllib.request.Request(u.scheme + "://" + u.netloc + full_path, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b"{}"


def market_check(ticker, env):
    base = DEMO_BASE if env == "demo" else UPSTREAM
    st, body = fetch_upstream(base + "/markets/" + urllib.parse.quote(ticker))
    if st >= 400:
        raise TradeError("Couldn't look up that market on Kalshi (HTTP %d)." % st)
    m = json.loads(body.decode("utf-8", "ignore") or "{}").get("market") or {}
    if str(m.get("status", "")).lower() not in ("open", "active"):
        raise TradeError("That market isn't open for trading.")
    try:
        close = time.mktime(time.strptime(str(m.get("close_time"))[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    except Exception:
        close = None
    return m, close


_ob_cache = {}


def _orderbook_body(ticker, env, max_age=0.0):
    """Kalshi's order book body for a market. Orders always read it fresh (max_age 0); the price lookups the page uses for deciding
    share one reading for a short moment so they don't multiply the requests."""
    key = (env, ticker)
    hit = _ob_cache.get(key)
    if max_age > 0 and hit and time.time() - hit[0] < max_age:
        return hit[1], hit[2]
    base = DEMO_BASE if env == "demo" else UPSTREAM
    st, body = fetch_upstream(base + "/markets/" + urllib.parse.quote(ticker) + "/orderbook")
    if max_age > 0:
        if len(_ob_cache) > 100:
            _ob_cache.clear()
        _ob_cache[key] = (time.time(), st, body)
    return st, body


def book_levels(ticker, side, env, max_age=0.0):
    """The bids that a buy of `side` would match against, as [(cents, contracts), ...] from Kalshi's public order book
    (None if it can't be read). Buying YES is matched by NO bids and buying NO by YES bids; a bid at b cents is an ask of 100-b."""
    try:
        st, body = _orderbook_body(ticker, env, max_age)
        if st >= 400:
            return None
        d = json.loads(body.decode("utf-8", "ignore") or "{}")
        ob = d.get("orderbook_fp") if isinstance(d.get("orderbook_fp"), dict) else d.get("orderbook")
        if not isinstance(ob, dict):
            return None
        opp = "no" if side == "yes" else "yes"
        levels = None
        for k in (opp + "_dollars", opp, opp + "_fp"):
            if isinstance(ob.get(k), list):
                levels = ob[k]
                break
        if levels is None:
            return None
        out = []
        for lv in levels:
            p, q = _f(lv[0]), _f(lv[1])
            if p is None or q is None:
                return None
            dollars = (isinstance(lv[0], str) and "." in lv[0]) or (isinstance(lv[0], float) and 0 < lv[0] < 1)      # "0.06" or 0.06 are dollars; 6 is cents
            out.append((p * 100 if dollars else p, q))
        return out
    except Exception:
        return None


def ask_snapshot(ticker, env):
    """What each side can really be bought for right now, from the order book (the same price an order would match against):
    {"yes_ask": cents|None, "no_ask": cents|None, "yes_qty": contracts at that price, "no_qty": ...}. None means nothing is for sale."""
    out = {"ok": True, "ts": time.time()}
    for side in ("yes", "no"):
        lv = book_levels(ticker, side, env, max_age=0.8)
        if lv is None:
            return {"ok": False, "ts": time.time()}
        live = [(p, q) for p, q in lv if q > 0]
        top = max((p for p, q in live), default=None)
        out[side + "_ask"] = None if top is None else round(100 - top, 2)
        out[side + "_qty"] = 0 if top is None else sum(q for p, q in live if abs(p - top) < 1e-9)
        # the whole ladder, cheapest first: [[ask in cents, contracts for sale at that price], ...] (a fake bet is priced level by level)
        by = {}
        for p, q in live:
            k = round(100 - p, 2)
            by[k] = by.get(k, 0) + q
        out[side + "_lv"] = [[k, round(by[k], 2)] for k in sorted(by)[:12]]
    return out


def depth_at(levels, price):
    """Contracts that could be bought at `price` cents or better, given the matching bids from book_levels."""
    if levels is None:
        return None
    need = 100 - price
    return sum(q for p, q in levels if p >= need - 1e-9)


def book_depth(ticker, side, price, env):
    return depth_at(book_levels(ticker, side, env), price)


def _quote_cents(m, k):
    v = _f(m.get(k + "_dollars"))
    if v is not None:
        return v * 100
    return _f(m.get(k))


def _ask_cents(m, side):
    a = _quote_cents(m, side + "_ask")
    return a if a else None


def live_ask(m, side, levels):
    """The cheapest price at which `side` can be bought right now, worked out three ways (the market's own ask, 100 minus the other
    side's best bid, and the order book) so one odd or stale field can't wrongly make a bet look too expensive. Returns (cents, notes)."""
    opp = "no" if side == "yes" else "yes"
    c = {}
    a1 = _ask_cents(m, side)
    if a1 is not None:
        c["market ask"] = a1
    b = _quote_cents(m, opp + "_bid")
    if b:
        c["from the other side's bid"] = 100 - b
    if levels:
        top = max((p for p, q in levels if q > 0), default=None)
        if top is not None:
            c["order book"] = 100 - top
    c = {k: v for k, v in c.items() if v is not None and 0 < v <= 100}
    shown = ", ".join("%d¢ x%g" % (round(p), q) for p, q in sorted(levels, reverse=True)[:3]) if levels else ""
    note = ", ".join("%s %d¢" % (k, round(v)) for k, v in c.items()) + (("; best bids on the other side: " + shown) if shown else ("; the book is empty" if levels is not None else ""))
    if levels is not None:        # the order book is what an order actually matches against, so it decides when it can be read
        return c.get("order book"), note
    return (min(c.values()) if c else None), note


_exec_lock = threading.Lock()


def place_order(body):
    with _exec_lock:                       # one order at a time, so each bankroll check sees every earlier order
        return _place_order(body)


def _place_order(body):
    t = trade_cfg()
    key_id, env = acct_config()
    ticker = str(body.get("ticker") or "")
    side = str(body.get("side") or "").lower()
    try:
        count, price = int(body.get("count")), int(body.get("price"))
    except (TypeError, ValueError):
        raise TradeError("The bet details were incomplete.")
    row = {"t": time.time(), "day": time.strftime("%Y-%m-%d"), "time": time.strftime("%Y-%m-%d %H:%M:%S"), "env": env, "ticker": ticker,
           "side": side, "count": count, "price_cents": price, "filled": False, "cost_total": 0.0,
           "src": body.get("src") if body.get("src") in ("manual", "sim", "auto") else "manual",
           "w": _f(body.get("w")), "sym": sym_of(ticker) or str(body.get("sym") or "")[:12], "conf": _f(body.get("conf")),
           "agree": _f(body.get("agree")), "opp": _f(body.get("opp"))}      # how many other coins qualified the same / the opposite way when an Auto bet was placed
    try:
        if not t["trading"]:
            raise TradeError("Betting is switched off. Turn it on in Menu > Kalshi account.")
        s = acct_status()
        if not s["ready"]:
            raise TradeError("Your Kalshi key isn't set up yet.")
        if not TICKER_RE.match(ticker):
            raise TradeError("Only 15-minute crypto markets can be bought from here.")
        if side not in ("yes", "no"):
            raise TradeError("The side must be YES or NO.")
        if not (1 <= price <= 99) or not (1 <= count <= 10000):
            raise TradeError("That price or number of contracts is out of range.")
        fee = est_fee(count, price)
        cost = count * price / 100.0 + fee
        bud_ref = cost                                   # what this bet may spend, at its limit price
        row["est_cost"] = round(cost, 4)
        avail_cap = None
        if row["src"] in ("sim", "auto"):
            bk = budget_stats(env).get(row["src"], {}).get(sym_of(ticker) if row["src"] == "sim" else "*")
            if not bk or bk["bank"] <= 0:
                raise TradeError("No real money is allocated to this (or it is all gone). Allocate some first.")
            avail_cap = bk["avail"]
            if cost > bk["avail"] + 1e-9:
                raise TradeError("This bet would cost about $%.2f but only $%.2f is left in its real bankroll." % (cost, max(bk["avail"], 0)))
        if row["src"] == "manual":       # a hand-placed bet can only use cash that no mode has allocated
            sm = acct_summary()
            if sm.get("ok") and sm.get("balance") is not None:
                held = sum(max(v["avail"], 0) for ks in budget_stats(env).values() for v in ks.values())
                if cost > sm["balance"] - held + 1e-9:
                    raise TradeError("This bet would cost about $%.2f but only $%.2f of your cash isn't allocated to a mode." % (cost, max(sm["balance"] - held, 0)))
        bud_in = _f(body.get("budget"))                  # the stake the page meant to spend (the whole contracts it could buy leave a few cents over)
        if row["src"] in ("sim", "auto") and bud_in and bud_in > cost:
            bud_ref = max(cost, min(bud_in, avail_cap) if avail_cap else bud_in)
        if row["src"] != "manual" and any(r.get("src") == row["src"] and r.get("ticker") == ticker and r.get("env") == env and r.get("order_id")
                                          for r in live_rows()):
            raise TradeError("Already bet on this market from this mode.")
        with order_lock:
            gap = 1.5 if row["src"] == "manual" else 0.25
            wait = gap - (time.time() - _last_order[0])
            if wait > 0:
                if row["src"] == "manual":
                    raise TradeError("Slow down: one bet at a time.")
                time.sleep(wait)                         # automatic bets queue up instead of being refused
            _last_order[0] = time.time()
        m, close = market_check(ticker, env)
        if close is not None and close - time.time() < 6:
            raise TradeError("That market is about to close.")
        levels = book_levels(ticker, side, env)
        ask, ask_note = live_ask(m, side, levels)
        maxp, slack = _f(body.get("max_price")), _f(body.get("slack"))
        if maxp is not None and ask is not None and row["src"] != "manual":
            # the page's price is a few seconds old. Re-price from Kalshi's live ask right now: pay up to `slack` cents over it, but never more
            # than max_price (the most this bet is worth given its estimated chance), and never spend more than the bet was budgeted for.
            maxp = int(maxp)
            live = int(math.ceil(ask - 1e-9))
            if live > maxp:
                raise TradeError("The price is now %d¢, above the %d¢ this bet is worth, so it wasn't placed. (%s)" % (live, maxp, ask_note))
            new = max(1, min(99, maxp, live + int(max(0, min(slack or 0, 5)))))
            if new != price:
                budget = bud_ref
                if row["src"] == "sim" and avail_cap:          # a Timed bet uses its whole bankroll, so a price that moved up may use all of it
                    budget = max(budget, avail_cap)
                bud_ref = budget
                # size the bet at the live price so the whole budget is used (the estimate was a few seconds old), then use whatever is left
                # over as room for the limit, so even a fill at the limit can never cost more than the budget
                cnt = count
                while cnt < 5000 and (cnt + 1) * live / 100.0 + est_fee(cnt + 1, live) <= budget + 1e-9:
                    cnt += 1
                while cnt > 1 and cnt * live / 100.0 + est_fee(cnt, live) > budget + 1e-9:
                    cnt -= 1
                price = new
                while price > live and cnt * price / 100.0 + est_fee(cnt, price) > budget + 1e-9:
                    price -= 1
                count = cnt
                row["price_cents"] = price
                if count * price / 100.0 + est_fee(count, price) > budget + 1e-9:
                    raise TradeError("The price moved up to %d¢ and the bet no longer fits its budget." % price)
                row["count"] = count
                cost = count * price / 100.0 + est_fee(count, price)
                row["est_cost"] = round(cost, 4)
        if ask is not None and price > ask + 5:
            raise TradeError("Your price (%d¢) is well above the current ask (%d¢). Refresh and try again." % (price, ask))
        # Kalshi's V2 orders are always quoted on the YES side: buying YES is a "bid" at the YES price, and buying NO is an "ask" (selling
        # YES) at 100 minus the NO price, which is the same position. Fill-or-kill: it fills completely at this price or better, or not at all.
        yes_px = price if side == "yes" else 100 - price
        depth = depth_at(levels, price)
        if depth is not None:
            if depth < 1:
                raise TradeError("Nothing is for sale at %d¢ or better right now, so nothing was bought. (%s)" % (price, ask_note))
            if depth < count:                              # a fill-or-kill order for more than is available would just be killed
                count = int(depth)
                row["count"] = count
                row["note"] = "reduced to the %d contracts available" % count
                fee = est_fee(count, price)
                cost = count * price / 100.0 + fee
                row["est_cost"] = round(cost, 4)
        fcount = float(count)
        if FRAC["ok"] and row["src"] in ("sim", "auto"):
            # top up with a fraction of a contract: the most that still fits the budget (even at the limit price) and the contracts for sale
            for step in range(99, 0, -1):
                c2 = count + step / 100.0
                if depth is not None and c2 > depth + 1e-9:
                    continue
                if c2 * price / 100.0 + est_fee(c2, price) <= bud_ref + 1e-9:
                    fcount = round(c2, 2)
                    break
            if fcount != count:
                row["count"] = fcount
                cost = fcount * price / 100.0 + est_fee(fcount, price)
                row["est_cost"] = round(cost, 4)
        order = {"ticker": ticker, "side": "bid" if side == "yes" else "ask", "count": "%.2f" % fcount, "price": "%.2f" % (yes_px / 100.0),
                 "time_in_force": "fill_or_kill", "self_trade_prevention_type": "taker_at_cross",
                 "client_order_id": "kd-%d-%s" % (int(time.time() * 1000), os.urandom(3).hex())}
        row["client_order_id"] = order["client_order_id"]
        base = _bases(env)[0]
        st, rb = signed_post(base, "/portfolio/events/orders", order)
        data = json.loads(rb.decode("utf-8", "ignore") or "{}")
        if st in (400, 422) and fcount != count and FRAC_ERR.search(acct_error_text(st, data) + " " + json.dumps(data)):
            FRAC["ok"] = False                           # Kalshi refused the fraction: nothing was bought, so re-send the same bet as whole contracts
            log("fractional count refused, using whole contracts from now on: %s" % acct_error_text(st, data))
            fcount = float(count)
            order["count"] = "%.2f" % fcount
            order["client_order_id"] = "kd-%d-%s" % (int(time.time() * 1000), os.urandom(3).hex())
            row["client_order_id"] = order["client_order_id"]
            row["count"] = count
            row["note"] = ((row.get("note") + "; ") if row.get("note") else "") + "Kalshi refused a fractional count, bought whole contracts"
            cost = count * price / 100.0 + est_fee(count, price)
            row["est_cost"] = round(cost, 4)
            st, rb = signed_post(base, "/portfolio/events/orders", order)
            data = json.loads(rb.decode("utf-8", "ignore") or "{}")
        if st >= 400:
            row["error"] = acct_error_text(st, data)
            raise TradeError(row["error"])
        o = data.get("order") if isinstance(data.get("order"), dict) else data
        fc = _f(o.get("fill_count"))
        if fc is None:
            fc = _f(o.get("fill_count_fp"))
        fc = fc or 0
        spend = fees = 0.0
        if fc > 0:
            avg = _f(o.get("average_fill_price"))               # per contract, quoted on the YES side
            per_fee = _f(o.get("average_fee_paid"))
            lim = price / 100.0
            if avg is not None and 0 < avg < 1:
                per = avg if side == "yes" else 1.0 - avg
                if side == "no" and per > lim + 0.005 and avg <= lim + 0.005:
                    per = avg                                   # reported in NO terms instead
                spend = fc * min(per, lim)                      # a fill-or-kill limit order can never cost more than its limit
            else:
                spend = fc * lim
            fees = fc * per_fee if per_fee is not None else est_fee(int(fc), price)
        row.update(order_id=o.get("order_id"), status="executed" if fc > 0 else "not filled", filled=bool(fc > 0), fill_count=fc,
                   cost=round(spend, 4), fees=round(fees, 4), cost_total=round(spend + fees, 4))
        if row["filled"]:                       # shortly after a fill, pick up Kalshi's own record of the price and fee actually paid
            threading.Timer(3.0, lambda: annotate(live_rows())).start()
        acct_cache["data"] = None
        return {"ok": True, "filled": row["filled"], "fill_count": fc, "cost": row["cost_total"], "status": row["status"],
                "message": ("Bought %g contracts for $%.2f." % (fc, row["cost_total"])) if row["filled"] else "Not filled: the price moved before it could complete. Nothing was bought."}
    except TradeError as e:
        row["refused"] = str(e)
        return {"ok": False, "error": str(e)}
    except Exception as e:
        log("order failed:\n" + traceback.format_exc())
        row["refused"] = "error: %s" % e
        return {"ok": False, "error": "The order couldn't be sent (%s). It may or may not have gone through; check the Kalshi site before trying again." % e}
    finally:
        try:
            live_append(row)
        except Exception:
            pass


def acct_info():
    t = trade_cfg()
    s = acct_status()
    rs = load_settings().get("kalshi_resume") or {}
    resume = {"auto": bool(rs.get("auto")) and t["trading"], "sim": bool(rs.get("sim")) and t["trading"]}      # which Start real betting buttons were on when the app last ran; nothing resumes while betting is switched off
    s.update(trading=t["trading"], max_bet=t["max_bet"], daily=t["daily"], spent_today=round(spent_today(s["env"]), 2), build=HELPER_BUILD, resume=resume)
    return s


def acct_set(body):
    cfg = load_settings()
    if "key_id" in body:
        kid = str(body["key_id"]).strip()
        if kid and not re.match(r"^[A-Za-z0-9\-]{8,80}$", kid):
            raise ValueError("That doesn't look like a Key ID.")
        cfg["kalshi_key_id"] = kid
        if not kid:
            cfg["kalshi_trading"] = False
    if body.get("env") in ("prod", "demo") and body["env"] != ("demo" if cfg.get("kalshi_env") == "demo" else "prod"):
        cfg["kalshi_env"] = body["env"]
        cfg["kalshi_trading"] = False                                   # a new environment always starts with betting off
    for k, name in (("max_bet", "kalshi_max_bet"), ("daily", "kalshi_daily")):
        if k in body:
            v = float(body[k])
            if not (0.5 <= v <= 100000):
                raise ValueError("Limits must be at least $0.50.")
            cfg[name] = v
    if "trading" in body:
        cfg["kalshi_trading"] = bool(body["trading"])
    if isinstance(body.get("resume"), dict):
        cfg["kalshi_resume"] = {"auto": bool(body["resume"].get("auto")), "sim": bool(body["resume"].get("sim"))}
    if not cfg.get("kalshi_trading"):
        cfg["kalshi_resume"] = {"auto": False, "sim": False}            # betting switched off (by you, a new environment, or a removed key): nothing may restart by itself
    save_settings(cfg)
    acct_cache["data"] = None
    return acct_info()


class Handler(BaseHTTPRequestHandler):
    server_version = "KalshiHelper/2.0"

    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _send(self, status, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _own_origin_ok(self):
        """Account requests must come from the dashboard page served by this helper: right Host (stops DNS-rebinding tricks) and, when the
        browser says which site sent it, that site must be this helper itself. Other web pages can't read your account or place bets."""
        port = self.server.server_address[1]
        if (self.headers.get("Host") or "").lower() not in ("127.0.0.1:%d" % port, "localhost:%d" % port):
            return False
        org = self.headers.get("Origin")
        if org is not None and org not in ("http://127.0.0.1:%d" % port, "http://localhost:%d" % port):
            return False
        return self.headers.get("Sec-Fetch-Site", "same-origin") in ("same-origin", "none")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.path
        if not path.startswith("/ping"):
            last_active[0] = time.time()
        if path.startswith("/settings"):
            cfg = load_settings()
            return self._send(200, json.dumps({"keep": KEEP[0], "data": DATA, "here": HERE, "version": local_version(), "started": START_T,
                                               "update_url": cfg.get("update_url", ""), "has_token": bool(cfg.get("update_token")), "frozen": FROZEN}))
        if path.startswith("/alive"):
            return self._send(200, json.dumps({"ok": True}))
        if path.startswith("/account/"):
            if not self._own_origin_ok():
                return self._send(403, json.dumps({"error": "forbidden"}))
            name = path.split("?")[0][len("/account/"):]
            try:
                if name == "status":
                    return self._send(200, json.dumps(acct_info()))
                if name == "summary":
                    return self._send(200, json.dumps(acct_summary("force=1" in path)))
                if name == "orders":
                    return self._send(200, json.dumps(annotate(live_rows()[-400:])[::-1]))
                if name == "budget":
                    return self._send(200, json.dumps({"env": acct_config()[1], "budget": budget_stats(acct_config()[1])}))
                if name == "ask":
                    q = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
                    tk = (q.get("ticker") or [""])[0]
                    if not TICKER_RE.match(tk):
                        return self._send(400, json.dumps({"error": "bad ticker"}))
                    return self._send(200, json.dumps(ask_snapshot(tk, acct_config()[1])))
                if name.startswith("market/"):
                    tk = urllib.parse.unquote(name[len("market/"):])
                    if not TICKER_RE.match(tk):
                        return self._send(400, json.dumps({"error": "bad ticker"}))
                    st, body = fetch_upstream((DEMO_BASE if acct_config()[1] == "demo" else UPSTREAM) + "/markets/" + urllib.parse.quote(tk))
                    return self._send(st, body)
            except Exception as e:
                log("account get failed:\n" + traceback.format_exc())
                return self._send(500, json.dumps({"error": str(e)}))
            return self._send(404, json.dumps({"error": "not found"}))
        if path.startswith("/kalshi/"):
            return self.proxy(path[len("/kalshi"):])
        if path.startswith("/data/"):
            return self.data_get(path.split("?")[0][len("/data/"):])
        if path.startswith("/ping"):
            return self._send(200, json.dumps({"ok": True, "app": "kalshi-helper", "data": DATA, "here": HERE, "page": find_dashboard(), "started": START_T}))
        if path in ("/", "/index.html") or path.split("?")[0].endswith(".html"):
            f = find_dashboard()
            if not f:
                return self._send(404, "kalshi_dashboard_v4.html not found next to kalshi_helper.py", "text/plain")
            with open(f, "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path.startswith("/bye"):
            bye_at[0] = time.time()
            return self._send(200, "{}")
        if self.path.startswith("/update"):
            org = self.headers.get("Origin") or ""
            local = (not org) or org == "null" or bool(re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", org))
            if self.headers.get("X-Kalshi") != "1" or not local:
                return self._send(403, json.dumps({"error": "forbidden"}))
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                cfg = load_settings()
                if "url" in body:
                    cfg["update_url"] = str(body["url"]).strip()
                if body.get("token"):
                    cfg["update_token"] = str(body["token"]).strip()
                if body.get("clear_token"):
                    cfg.pop("update_token", None)
                save_settings(cfg)
                port = self.server.server_address[1]
                res = update_apply(port) if body.get("action") == "apply" else update_check()
                self._send(200, json.dumps(res))
                if res.get("restart"):
                    restart_self(port)
                    threading.Timer(1.0, self.server.shutdown).start()
            except Exception as e:
                log("update failed:\n" + traceback.format_exc())
                self._send(200, json.dumps({"ok": False, "error": str(e)}))
            return
        if self.path.startswith("/restart"):
            org = self.headers.get("Origin") or ""
            local = (not org) or org == "null" or bool(re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", org))
            if self.headers.get("X-Kalshi") != "1" or not local:
                return self._send(403, json.dumps({"error": "forbidden"}))
            self._send(200, json.dumps({"ok": True}))
            log("restart requested")
            restart_self(self.server.server_address[1])
            threading.Timer(1.0, self.server.shutdown).start()
            return
        if self.path.startswith("/account/"):
            if not self._own_origin_ok() or self.headers.get("X-Kalshi") != "1":
                return self._send(403, json.dumps({"ok": False, "error": "Open the dashboard from its icon (or http://127.0.0.1) to use your Kalshi account."}))
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                name = self.path.split("?")[0][len("/account/"):]
                if name == "order":
                    return self._send(200, json.dumps(place_order(body)))
                if name == "config":
                    if "budgets" in body:
                        return self._send(200, json.dumps({"ok": True, "budget": budget_set_many(body["budgets"])}))
                    if "budget" in body:
                        return self._send(200, json.dumps({"ok": True, "budget": budget_set(body["budget"])}))
                    return self._send(200, json.dumps({"ok": True, "status": acct_set(body)}))
                if name == "folder":
                    os.makedirs(KEYS_DIR, exist_ok=True)
                    open_folder(KEYS_DIR)
                    return self._send(200, json.dumps({"ok": True, "path": KEYS_DIR}))
            except ValueError as e:
                return self._send(200, json.dumps({"ok": False, "error": str(e)}))
            except Exception as e:
                log("account post failed:\n" + traceback.format_exc())
                return self._send(200, json.dumps({"ok": False, "error": str(e)}))
            return self._send(404, json.dumps({"error": "not found"}))
        if self.path.startswith("/open") or self.path.startswith("/settings"):
            org = self.headers.get("Origin") or ""
            local = (not org) or org == "null" or bool(re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", org))
            if self.headers.get("X-Kalshi") != "1" or not local:
                return self._send(403, json.dumps({"error": "forbidden"}))
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                if self.path.startswith("/open"):
                    target = {"data": DATA, "app": HERE}.get(body.get("what"))
                    if not target:
                        return self._send(400, json.dumps({"error": "unknown folder"}))
                    os.makedirs(target, exist_ok=True)
                    open_folder(target)
                    return self._send(200, json.dumps({"ok": True, "path": target}))
                cfg = load_settings()
                if "keep" in body:
                    cfg["keep"] = bool(body["keep"])
                    KEEP[0] = cfg["keep"]
                save_settings(cfg)
                return self._send(200, json.dumps({"ok": True, "keep": KEEP[0]}))
            except Exception as e:
                log("open/settings failed:\n" + traceback.format_exc())
                return self._send(400, json.dumps({"error": str(e)}))
        if self.path.startswith("/quit"):
            if self.headers.get("X-Kalshi") != "1":
                return self._send(403, json.dumps({"error": "forbidden"}))
            self._send(200, json.dumps({"ok": True, "stopping": True}))
            log("stop requested")
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        last_active[0] = time.time()
        if self.path.startswith("/data/prices"):
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if n > 8 * 1024 * 1024:
                    return self._send(413, json.dumps({"error": "too large"}))
                return self._send(200, json.dumps(save_prices(json.loads(self.rfile.read(n).decode("utf-8") or "{}"))))
            except Exception as e:
                log("price log failed: %s" % e)
                return self._send(400, json.dumps({"error": str(e)}))
        if not self.path.startswith("/data/save"):
            return self._send(404, json.dumps({"error": "not found"}))
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 60 * 1024 * 1024:
                return self._send(413, json.dumps({"error": "too large"}))
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            self._send(200, json.dumps(save_data(body)))
        except Exception as e:
            log("save failed:\n" + traceback.format_exc())
            self._send(400, json.dumps({"error": str(e)}))

    def data_get(self, name):
        with lock:
            if name == "state":
                return self._send(200, json.dumps({"sig": store["sig"][-5000:], "cal": list(cal_recent), "fin": store["fin"][-2000:], "sim": store["sim"][-2000:], "simstate": read_simstate()}))
            if name == "signals":
                return self._send(200, json.dumps(store["sig"]))
            if name == "auto":
                return self._send(200, json.dumps([r for r in store["sim"] if r.get("cp") == "AUTO"]))
            if name == "info":
                return self._send(200, json.dumps({"dir": DATA, "signals": len(store["sig"]), "final_calls": len(store["fin"]),
                                                   "calibration_samples": CAL_COUNT[0], "sim_trades": len(store["sim"])}))
            if name in ("signals.csv", "final_calls.csv", "calibration.csv", "calibration_summary.json", "sim_trades.csv", "sim_state.json"):
                p = os.path.join(DATA, name)
                if os.path.isfile(p):
                    with open(p, "rb") as f:
                        return self._send(200, f.read(), "application/json" if name.endswith(".json") else "text/csv")
                return self._send(404, json.dumps({"error": "no data yet"}))
        self._send(404, json.dumps({"error": "not found"}))

    def proxy(self, rest):
        if not any(rest == a or rest.startswith(a + "/") or rest.startswith(a + "?") for a in ALLOWED):
            return self._send(403, json.dumps({"error": "path not allowed"}))
        url = UPSTREAM + rest
        now = time.time()
        with lock:
            hit = cache.get(url)
            if hit and now - hit[0] < CACHE_TTL:
                return self._send(hit[1], hit[2])
        status, body = fetch_upstream(url)
        with lock:
            cache[url] = (time.time(), status, body)
            if len(cache) > 200:
                cache.clear()
        self._send(status, body)


def find_browser():
    """A Chromium-based browser (Edge, Chrome, Brave...) that can show the dashboard as its own app window."""
    import shutil
    env = os.environ.get("KALSHI_BROWSER")
    if env and os.path.isfile(env):
        return env
    c = []
    if platform.system() == "Windows":
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LocalAppData")):
            if base:
                c += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                      os.path.join(base, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")]
    elif platform.system() == "Darwin":
        for n in ("Microsoft Edge", "Google Chrome", "Brave Browser", "Chromium"):
            c.append("/Applications/%s.app/Contents/MacOS/%s" % (n, n))
    else:
        c += [shutil.which(n) or "" for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser", "brave-browser")]
    for p in c:
        if p and os.path.isfile(p):
            return p
    return None


def launch_ui(url, as_app=True):
    """Open the dashboard in its own window (no tabs or address bar). Returns the process, or None for a normal browser tab."""
    exe = find_browser() if as_app else None
    if exe:
        try:
            profile = os.path.join(HERE, "app_profile")      # separate profile: the process lasts as long as the window
            return subprocess.Popen([exe, "--app=" + url, "--user-data-dir=" + profile, "--no-first-run",
                                     "--no-default-browser-check", "--window-size=1320,940"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            log("could not start app window:\n" + traceback.format_exc())
    webbrowser.open(url)
    return None


SETTINGS_FILE = os.path.join(HERE, "settings.json")


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(d):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
    except Exception:
        log("could not save settings:\n" + traceback.format_exc())


def open_folder(path):
    """Show a folder in Explorer / Finder / the file manager."""
    if platform.system() == "Windows":
        os.startfile(path)                                   # noqa
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --------------------------------------------------------------------------- self-update
def parse_stamp(text):
    m = re.search(r"build (\d{4}-\d{2}-\d{2}[a-z]*)", text)
    return m.group(1) if m else None


def local_version():
    f = find_dashboard()
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            return parse_stamp(fh.read()) or "unknown"
    except Exception:
        return "unknown"


def http_get(url, token=None, timeout=20, extra=None):
    if "raw.githubusercontent.com" in url:      # GitHub caches raw files for ~5 minutes; a changing query string gets the newest copy
        url += ("&" if "?" in url else "?") + "cb=%d" % time.time_ns()
    headers = {"User-Agent": "kalshi-helper/2.0"}
    if extra:
        headers.update(extra)
    if token:
        headers["Authorization"] = "token " + token
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout,
                                    context=ssl_ctx()) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError("The update address answered HTTP %d (check the address%s)." % (e.code, " and token" if token else ""))
    except Exception as e:
        try:   # curl uses the system certificates (helps when this Python can't verify them)
            cmd = ["curl", "-sSfL", "--max-time", "25"] + (["-H", "Authorization: token " + token] if token else []) + [url]
            p = subprocess.run(cmd, capture_output=True, timeout=30)
            if p.returncode == 0 and p.stdout:
                return p.stdout
        except Exception:
            pass
        raise RuntimeError("Could not reach the update address: %s" % e)


def update_base(url):
    url = (url or "").strip()
    m = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$", url)
    if m:                                   # a plain repository link -> its raw files on the main branch
        url = "https://raw.githubusercontent.com/%s/%s/main/" % (m.group(1), m.group(2))
    if not url:
        raise RuntimeError("No update address set. Paste the address of your update folder first.")
    if not (url.lower().startswith("https://") or re.match(r"^http://(127\.0\.0\.1|localhost)[:/]", url.lower())):
        raise RuntimeError("The update address must start with https://")
    return url if url.endswith("/") else url + "/"


RAW_RE = re.compile(r"^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.*)$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def is_pinned(base):
    m = RAW_RE.match(base)
    return bool(m and SHA_RE.match(m.group(3)))


def pin_to_commit(base, token=None):
    """GitHub serves a branch's files from a cache that can lag by several minutes and can hand out version.json and the
    files from different moments (that is what caused 'did not match its checksum'). A single commit never changes, so
    look up the newest commit and read everything from that one. If the lookup fails, the branch address is used as before."""
    m = RAW_RE.match(base)
    if not m or SHA_RE.match(m.group(3)):
        return base
    owner, repo, ref, sub = m.groups()
    try:
        api = "https://api.github.com/repos/%s/%s/commits/%s?cb=%d" % (owner, repo, urllib.parse.quote(ref, safe=""), time.time_ns())
        sha = http_get(api, token, 10, {"Accept": "application/vnd.github.sha"}).decode("ascii", "ignore").strip()
        if SHA_RE.match(sha):
            return "https://raw.githubusercontent.com/%s/%s/%s/%s" % (owner, repo, sha, sub)
    except Exception:
        pass
    return base


def update_manifest(cfg):
    base = update_base(cfg.get("update_url"))
    token = cfg.get("update_token")
    pinned = pin_to_commit(base, token)
    last = None
    for b in ([pinned, base] if pinned != base else [base]):
        try:
            man = json.loads(http_get(b + "version.json", token).decode("utf-8"))
            return b, man, str(man["version"])
        except RuntimeError as e:
            last = e
        except Exception:
            last = RuntimeError("version.json at that address could not be read.")
    raise last


def is_newer(remote, local):
    """True only when the remote build stamp is later than ours (never step back to an older copy)."""
    if local in ("", "unknown", None):
        return True
    return remote > local


def update_check():
    cfg = load_settings()
    base, man, ver = update_manifest(cfg)
    loc = local_version()
    return {"ok": True, "local": loc, "remote": ver, "available": is_newer(ver, loc), "notes": str(man.get("notes", ""))}


def restart_self(port):
    """Start a fresh copy of this helper (it waits for this one to exit), then shut this one down."""
    exe = sys.executable
    if platform.system() == "Windows":
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        exe = w if os.path.exists(w) else exe
    cmd = [exe, os.path.abspath(__file__), "--restart", "--no-browser", "--port", str(port)]
    if KEEP[0]:
        cmd.append("--keep-running")
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if platform.system() == "Windows":
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)


def update_apply(port):
    cfg = load_settings()
    base, man, ver = update_manifest(cfg)
    loc = local_version()
    if not is_newer(ver, loc):
        return {"ok": True, "updated": False, "local": loc, "remote": ver}
    names = man.get("files") or []
    hashes = man.get("sha256") or {}
    fetched, skipped = {}, []
    for name in names:
        if os.path.basename(name) != name or name.startswith(".") or not name.lower().endswith(UPDATE_EXT):
            raise RuntimeError("The update lists a file name that isn't allowed: %s" % name)
        if FROZEN and name.lower().endswith(".py"):
            skipped.append(name)
            continue
        body = http_get(base + urllib.request.quote(name), cfg.get("update_token"))
        for _try in range(1 if is_pinned(base) else 3):      # a stale cached copy can briefly disagree with version.json; ask again for a fresh one (not needed when reading a fixed commit)
            if name not in hashes or hashlib.sha256(body).hexdigest() == hashes[name].lower():
                break
            time.sleep(3)
            body = http_get(base + urllib.request.quote(name), cfg.get("update_token"))
        if name in hashes and hashlib.sha256(body).hexdigest() != hashes[name].lower():
            raise RuntimeError("%s did not match its checksum; nothing was changed." % name)
        if name.lower().endswith(".py"):
            try:
                compile(body, name, "exec")
            except SyntaxError as e:
                raise RuntimeError("%s is not valid Python (%s); nothing was changed." % (name, e))
        if name.lower().endswith(".html") and b"<html" not in body.lower():
            raise RuntimeError("%s does not look like a web page; nothing was changed." % name)
        fetched[name] = body
    if not fetched:
        raise RuntimeError("The update contained no files this copy can install.")
    bdir = os.path.join(HERE, "backup", "%s_%s" % (loc, time.strftime("%Y%m%d-%H%M%S")))
    os.makedirs(bdir, exist_ok=True)
    for name in fetched:
        cur = os.path.join(HERE, name)
        if os.path.isfile(cur):
            with open(cur, "rb") as a, open(os.path.join(bdir, name), "wb") as b:
                b.write(a.read())
    for name, body in fetched.items():
        tmp = os.path.join(HERE, name + ".new")
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, os.path.join(HERE, name))
    restart = any(n.lower().endswith(".py") for n in fetched)
    log("updated %s -> %s (%s)" % (loc, ver, ", ".join(fetched)))
    return {"ok": True, "updated": True, "local": loc, "remote": ver, "restart": restart, "backup": bdir, "skipped": skipped}


def running_info(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/ping" % port, timeout=1.5) as r:
            d = json.loads(r.read().decode())
            return d if d.get("app") == "kalshi-helper" else None
    except Exception:
        return None


def already_running(port):
    return running_info(port) is not None


def serve(port, open_browser):
    try:
        return _serve(port, open_browser)
    except Exception:
        log("startup crashed:\n" + traceback.format_exc())
        print("The helper crashed. Details were saved to helper.log next to this file:\n" + traceback.format_exc())
        return 1


def _serve(port, open_browser):
    url = "http://127.0.0.1:%d/" % port
    info = running_info(port)
    if info is not None and (not info.get("here") or os.path.normcase(os.path.abspath(info["here"])) != os.path.normcase(os.path.abspath(HERE))):
        # a helper from another folder or an older version is running and would keep serving the OLD page: replace it
        log("replacing helper running from: %s" % info.get("here"))
        stop(port)
        for _ in range(10):
            time.sleep(0.4)
            if running_info(port) is None:
                break
        info = running_info(port)
        if info is not None:
            print("An older helper is still running and could not be closed automatically (it is serving: %s).\n"
                  "End it in Task Manager (python.exe / pythonw.exe / KalshiDashboard.exe), then start this again." % (info.get("page") or "an old page"))
            return 1
    if info is not None:
        if open_browser:
            launch_ui(url, not TAB[0])
        return 0
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        print("Could not start on port %d (%s). Is something else using it? Try --port 8790." % (port, e))
        return 1
    load_store()
    print("Kalshi helper running.\n  Dashboard: %s%s\n  Saving data to: %s\nLeave this window open. Press Ctrl+C to stop."
          % (url, "" if find_dashboard() else "   (dashboard html not found next to this file!)", DATA))
    def ui():
        proc = launch_ui(url, not TAB[0])
        if proc is not None and not KEEP[0]:
            proc.wait()                       # the app window was closed
            log("app window closed")
            time.sleep(8)
            if time.time() - last_active[0] > 8:   # nobody else (e.g. a second window) is still using it
                srv.shutdown()
    if open_browser:
        threading.Timer(0.6, lambda: threading.Thread(target=ui, daemon=True).start()).start()

    def watchdog():
        while True:
            time.sleep(3)
            if KEEP[0]:
                continue
            now = time.time()
            if bye_at[0] and now - bye_at[0] > 6 and last_active[0] <= bye_at[0]:
                log("dashboard closed - stopping")
                srv.shutdown()
                return
            idle = (now - last_active[0] > IDLE_AFTER_PAGE) if last_active[0] else (now - START_T > IDLE_NEVER_USED)
            if idle:
                log("no dashboard activity - closing")
                srv.shutdown()
                return
    threading.Thread(target=watchdog, daemon=True).start()

    def self_watch():              # if this program file is replaced (an update, or a new copy dropped in), restart so the new code is what runs
        if FROZEN:
            return
        me = os.path.abspath(__file__)

        def digest():
            try:
                with open(me, "rb") as f:
                    return hashlib.sha256(f.read()).hexdigest()
            except OSError:
                return None
        base = digest()
        while True:
            time.sleep(4)
            now = digest()
            if now is None or now == base:
                continue
            time.sleep(2)                                   # let a copy in progress finish
            if digest() != now:
                continue
            try:
                with open(me, "rb") as f:
                    compile(f.read(), me, "exec")
            except Exception:
                base = now                                  # a half-written or broken file: don't restart into it
                continue
            log("kalshi_helper.py changed on disk - restarting")
            try:
                restart_self(port)
            except Exception as e:
                log("self-restart failed: %s" % e)
                base = now
                continue
            time.sleep(0.5)
            srv.shutdown()
            return
    threading.Thread(target=self_watch, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


# --------------------------------------------------------------------------- installer
def desktop_dir(system):
    if os.environ.get("KALSHI_DESKTOP"):
        return os.environ["KALSHI_DESKTOP"]
    home = os.path.expanduser("~")
    if system == "Windows":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)   # CSIDL_DESKTOPDIRECTORY
            if buf.value:
                return buf.value
        except Exception:
            pass
    return os.path.join(home, "Desktop")


def plan(system, py, script, port):
    """Return (files, post). files = [(path, content, executable)]; nothing is written here."""
    home = os.path.expanduser("~")
    desk = desktop_dir(system)
    url = "http://127.0.0.1:%d/" % port
    files, post = [], []
    def q(x): return '"%s"' % x
    run = [py] if FROZEN else [py, script]
    if system == "Windows":
        pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
        pyw = pyw if os.path.exists(pyw) else py
        startup = os.path.join(os.environ.get("APPDATA", home), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        wrun = [py] if FROZEN else [pyw, script]
        files.append((os.path.join(desk, "Kalshi Dashboard.bat"),
                      '@echo off\r\nstart "" %s --port %d\r\n' % (" ".join(q(x) for x in wrun), port), False))
        post.append(("start_now", wrun + ["--port", str(port)]))
    elif system == "Darwin":
        plist = os.path.join(home, "Library", "LaunchAgents", "com.kalshi.dashboard.helper.plist")
        files.append((plist, """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.kalshi.dashboard.helper</string>
  <key>ProgramArguments</key><array><string>%s</string><string>%s</string><string>--no-browser</string><string>--port</string><string>%d</string></array>
  <key>RunAtLoad</key><false/><key>KeepAlive</key><false/>
</dict></plist>
""" % (py, script, port), False))
        files.append((os.path.join(desk, "Kalshi Dashboard.command"),
                      '#!/bin/bash\n# starts the helper if it is not already running, then opens the dashboard\n"%s" "%s" --port %d\n' % (py, script, port), True))
        post.append(("launchctl_load", plist))
    else:  # Linux and others
        files.append((os.path.join(home, ".config", "autostart", "kalshi-dashboard-helper.desktop"),
                      "[Desktop Entry]\nType=Application\nName=Kalshi Dashboard Helper\nExec=%s %s --no-browser --port %d\nX-GNOME-Autostart-enabled=true\n" % (py, script, port), False))
        files.append((os.path.join(desk, "Kalshi Dashboard.desktop"),
                      "[Desktop Entry]\nType=Application\nName=Kalshi Dashboard\nExec=%s %s --port %d\nTerminal=false\n" % (py, script, port), True))
        post.append(("start_now", [py, script, "--port", str(port)]))
    return files, post


def install(port, start=True):
    system = platform.system()
    script = os.path.abspath(__file__)
    if not find_dashboard():
        print("Put kalshi_dashboard_v4.html in the same folder as this file first:\n  %s" % HERE)
        return 1
    files, post = plan(system, sys.executable, script, port)
    if system == "Windows":      # older versions started a hidden helper at every login; no longer needed
        old = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "Kalshi Dashboard Helper.bat")
        try:
            if os.path.exists(old):
                os.remove(old)
                print("removed old start-at-login file:", old)
        except Exception:
            pass
    for path, content, ex in files:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="") as f:
            f.write(content)
        if ex:
            os.chmod(path, 0o755)
        print("created:", path)
    if start:
        for kind, arg in post:
            try:
                if kind == "launchctl_load":
                    subprocess.run(["launchctl", "unload", arg], capture_output=True)
                    subprocess.run(["launchctl", "load", "-w", arg], capture_output=True)
                elif system == "Windows":
                    subprocess.Popen(arg, creationflags=0x00000008 | 0x00000200, close_fds=True)
                else:
                    subprocess.Popen(arg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            except Exception as e:
                print("could not start it right now (%s); it will start at your next login." % e)
        time.sleep(1.5)
    print("\nDone. From now on: double-click \"Kalshi Dashboard\" on your Desktop to open it. "
          "It closes itself when you close the dashboard window. (http://127.0.0.1:%d/)\n"
          "Keep this folder where it is:\n  %s" % (port, HERE))
    return 0


def uninstall(port):
    system = platform.system()
    files, post = plan(system, sys.executable, os.path.abspath(__file__), port)
    for kind, arg in post:
        if kind == "launchctl_load":
            subprocess.run(["launchctl", "unload", arg], capture_output=True)
    for path, _, _ in files:
        if os.path.exists(path):
            os.remove(path)
            print("removed:", path)
    print("Uninstalled. (A helper that is already running stops when you log out or restart.)")
    return 0


def stop(port):
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/quit" % port, data=b"{}", method="POST", headers={"X-Kalshi": "1"})
        urllib.request.urlopen(req, timeout=3).read()
        print("Helper stopped.")
    except Exception:
        print("Helper was not running (or is an older version: end it in Task Manager).")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Local Kalshi helper for the crypto dashboard")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true", help="don't open the dashboard in a browser")
    ap.add_argument("--install", action="store_true", help="one-time setup: desktop icon + start at login")
    ap.add_argument("--uninstall", action="store_true", help="remove the desktop icon and start-at-login")
    ap.add_argument("--stop", action="store_true", help="close a running helper")
    ap.add_argument("--tab", action="store_true", help="open in a normal browser tab instead of an app window")
    ap.add_argument("--restart", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--keep-running", action="store_true", help="don't close automatically when the dashboard page is closed")
    ap.add_argument("--no-start", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.stop:
        sys.exit(stop(a.port))
    if a.restart:                       # started by the updater: wait for the old copy to let go of the port
        for _ in range(60):
            if running_info(a.port) is None:
                break
            time.sleep(0.5)
    KEEP[0] = a.keep_running or bool(load_settings().get("keep"))
    TAB[0] = a.tab
    if a.install:
        sys.exit(install(a.port, start=not a.no_start))
    if a.uninstall:
        sys.exit(uninstall(a.port))
    sys.exit(serve(a.port, not a.no_browser))


if __name__ == "__main__":
    main()
