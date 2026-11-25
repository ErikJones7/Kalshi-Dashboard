"""Checks for kalshi_dashboard_v4.html in a headless browser (no network needed, no real money).
Run:  python3 tests/test_page.py        (needs: pip install playwright && playwright install chromium)"""
import os, re, sys, time
from playwright.sync_api import sync_playwright

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PAGE = "file://" + os.path.abspath(os.path.join(ROOT, "kalshi_dashboard_v4.html"))
FAILS = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: FAILS.append(m)

BAL = "Kalshi returned HTTP 400: insufficient balance"
def R(ago, est, filled=False, err=None, cost=0, now=None):
    return {"t": now - ago, "src": "auto", "env": "prod", "est_cost": est, "filled": filled, "cost_total": cost, "refused": err}

with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(PAGE); pg.wait_for_timeout(1500)
    now = pg.evaluate("Date.now()/1000"); reset = pg.evaluate("BAL_RESET")
    ok(not errs, "the page loads with no script errors: %s" % errs[:1])
    helper = open(os.path.join(ROOT, "kalshi_helper.py"), encoding="utf-8").read()
    hb = re.search(r'HELPER_BUILD = "([^"]+)"', helper).group(1)
    ok(pg.evaluate("HELPER_EXPECT") == hb, "the helper build the page expects matches the helper file (%s)" % hb)
    import json; ver = json.load(open(os.path.join(ROOT, "version.json")))["version"]
    ok(pg.inner_text("#build") == "build " + ver, "build stamp on the page matches version.json: " + pg.inner_text("#build"))

    def setup(orders, saved=None):
        pg.evaluate("s=>{try{localStorage.removeItem('k15balg');if(s)localStorage.setItem('k15balg',JSON.stringify(s))}catch(e){}}", saved)
        pg.evaluate("o=>{acct.info={env:'prod',build:HELPER_EXPECT,ready:true,trading:true};acct.sum={ok:true,balance:225};sim=false;acct.orders=o;"
                    "acct.bud={auto:{'*':{bank:227.89,avail:222,open:0,net:0,w:0,l:0,peak:230,since:1}}};balG.seeded=false;balG.cap=null;balG.n=0;balG.minRef=null;balSeedOnce()}", orders)
    state = lambda: pg.evaluate("({cap:balG.cap,n:balG.n,minRef:balG.minRef})")

    # ---- Kalshi cash guard
    new = [R(60, 28.99, err=BAL, now=now), R(900, 20.37, err=BAL, now=now), R(3600, 5.22, err=BAL, now=now), R(7200, 1.35, True, cost=1.34, now=now), R(9000, 3.1, True, cost=3.09, now=now)]
    new = [o for o in new if o["t"] > reset] or new
    setup(new); s = state()
    ok(s["minRef"] == 5.22 and s["cap"] == 3.13 and s["n"] == 3, "refusals since the last fill give a cap of 60%% of the smallest one: %s" % s)
    old = [dict(o, t=reset - 500 - i) for i, o in enumerate(new)]
    setup(old, saved={"cap": 3.13, "n": 3, "minRef": 5.22, "t": (reset - 100) * 1000, "k": "prod"}); s = state()
    ok(s["cap"] is None and s["n"] == 0, "refusals and a saved limit from before the money was moved are ignored: %s" % s)
    setup(new)
    pg.evaluate("balRefused(4)"); s = state(); ok(s["cap"] == 2.4 and s["minRef"] == 4, "a smaller refusal lowers the cap: %s" % s)
    pg.evaluate("balAccepted(1.5)"); ok(state()["cap"] == 2.4, "a bet well under the cap leaves it alone")
    pg.evaluate("balAccepted(2.3)"); ok(state()["cap"] == 3.59, "a bet near the cap raises it 50%")
    pg.evaluate("balAccepted(4.2)"); ok(state()["cap"] is None, "a bet as big as anything refused clears the limit")

    setup(new); pg.evaluate("()=>{real.auto=true;renderRealAuto()}")
    note = pg.inner_text("#arNote"); ok("insufficient balance" in note and "$3.13" in note, "the real Auto card shows the warning and the cap")
    pg.click("#balClear"); pg.wait_for_timeout(100); ok(state()["cap"] is None and pg.inner_text("#arNote") == "", "'Clear this limit' removes the cap and the warning")

    setup(new)
    r = pg.evaluate("""async()=>{
      lvPlan=(sym,side,stake)=>({ticker:'KXTEST',side,count:Math.floor(stake/0.9),price:90,cost:stake,cap:stake});
      let posts=0;apost=async()=>{posts++;return {ok:false,error:'Kalshi returned HTTP 400: insufficient balance'}};
      const r=await realMirror('auto','ETH','yes',20,{w:Date.now()/1000+300,p:0.95,agree:0,opp:0});
      return {r,posts,cap:balG.cap,txt:real.events[0]}}""")
    ok(r["r"] == "stop" and r["posts"] == 1, "a refused-for-balance bet is not retried: %s" % r["r"])
    ok("insufficient balance" in r["txt"] and "capped" in r["txt"], "the event line says why: " + r["txt"][-110:])
    pg.evaluate("o=>{acct.orders=o;balG.seeded=false;balG.cap=null;balG.n=0;balG.minRef=null;balSeedOnce()}", new)
    sizes = pg.evaluate("""()=>{window.__s=[];realMirror=(src,sym,side,st)=>{__s.push(st);return Promise.resolve('x')};autoSt.cap=0.2;
      realAuto({f:0.2},false,[{sym:'ETH',side:'yes',conf:0.95,agree:0,opp:0}],Date.now()/1000+300);return __s}""")
    ok(sizes == [3.13], "real Auto sizes its bet under the cap: %s" % sizes)
    pg.evaluate("balClear()")
    sizes = pg.evaluate("()=>{__s.length=0;realAuto({f:0.2},false,[{sym:'ETH',side:'yes',conf:0.95,agree:0,opp:0}],Date.now()/1000+300);return __s}")
    ok(len(sizes) == 1 and sizes[0] > 20, "with no cap it sizes from the bankroll again: %s" % sizes)
    # ---- Timed bets were removed from the page; the data they left is still carried along unchanged
    gone = pg.evaluate("['simCard','simOnBtn','simTbl','trTbl','simAt','simMin','simRealAll'].filter(i=>document.getElementById(i))")
    ok(gone == [], "the Timed bets card is gone from the page: %s" % gone)
    pg.evaluate("""()=>{const day=new Date().toLocaleDateString('en-CA'),o=(src,t,c,f)=>({filled:true,src,env:'prod',ticker:t,side:'yes',cost_total:c,fill_count:f,day});
      acct.info={env:'prod',ready:true,trading:true};acct.sum={ok:true,balance:225,positions:[]};sim=false;
      acct.orders=[o('auto','KXBTC15M-A',5,8),o('sim','KXSOL15M-C',4,6)];liveRes['KXBTC15M-A']='yes';liveRes['KXSOL15M-C']='yes';
      acct.bud={auto:{'*':{bank:227.89,avail:222,open:0,net:0,w:0,l:0,peak:230,since:1}}};real.auto=false;renderAcctCard()}""")
    rows = pg.evaluate("[...document.querySelectorAll('#acRes tr')].slice(1).map(r=>r.cells[0].innerText)")
    ok(rows == ["Auto mode", "All"], "the Kalshi account card has no Timed bets row: %s" % rows)
    ok(pg.evaluate("realStats().all.n") == 2, "an old Timed fill still counts in the account totals")
    sent = pg.evaluate("""async()=>{simSt={start:{BTC:5},tr:{},ref:9};simDef=22.22;simMode='zero';simGain=10;hBase='http://x';let body=null;
      hpost=async(p,o)=>{body=o;return {}};await saveToHelper();const s=body&&body.simstate;return s&&{simSt:s.simSt,simDef:s.simDef,simMode:s.simMode,simGain:s.simGain}}""")
    ok(sent == {"simSt": {"start": {"BTC": 5}, "tr": {}, "ref": 9}, "simDef": 22.22, "simMode": "zero", "simGain": 10},
       "saving to the data folder still sends Timed's saved state unchanged: %s" % sent)
    ok(not errs, "no script errors during the checks: %s" % errs[:1])
    b.close()

print("\n%d failed" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
