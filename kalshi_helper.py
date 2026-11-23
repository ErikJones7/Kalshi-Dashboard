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
import hashlib
import http.client
import json
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
CACHE_TTL = 0.8                                             # seconds; avoids hammering Kalshi
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
            local = (not org) or org == "null" or org.startswith("http://127.0.0.1") or org.startswith("http://localhost")
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
            local = (not org) or org == "null" or org.startswith("http://127.0.0.1") or org.startswith("http://localhost")
            if self.headers.get("X-Kalshi") != "1" or not local:
                return self._send(403, json.dumps({"error": "forbidden"}))
            self._send(200, json.dumps({"ok": True}))
            log("restart requested")
            restart_self(self.server.server_address[1])
            threading.Timer(1.0, self.server.shutdown).start()
            return
        if self.path.startswith("/open") or self.path.startswith("/settings"):
            org = self.headers.get("Origin") or ""
            local = (not org) or org == "null" or org.startswith("http://127.0.0.1") or org.startswith("http://localhost")
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
