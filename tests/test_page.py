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
      window.__lvPlan=window.__lvPlan||lvPlan;lvPlan=(sym,side,stake)=>({ticker:'KXTEST',side,count:Math.floor(stake/0.9),price:90,cost:stake,cap:stake});
      let posts=0;apost=async()=>{posts++;return {ok:false,error:'Kalshi returned HTTP 400: insufficient balance'}};
      const r=await realMirror('auto','ETH','yes',20,{w:Date.now()/1000+300,p:0.95,agree:0,opp:0});
      lvPlan=window.__lvPlan;return {r,posts,cap:balG.cap,txt:real.events[0]}}""")
    ok(r["r"] == "stop" and r["posts"] == 1, "a refused-for-balance bet is not retried: %s" % r["r"])
    ok("insufficient balance" in r["txt"] and "capped" in r["txt"], "the event line says why: " + r["txt"][-110:])
    pg.evaluate("o=>{acct.orders=o;balG.seeded=false;balG.cap=null;balG.n=0;balG.minRef=null;balSeedOnce()}", new)
    sizes = pg.evaluate("""()=>{window.__s=[];window.__rm=window.__rm||realMirror;realMirror=(src,sym,side,st)=>{__s.push(st);return Promise.resolve('x')};autoSt.cap=0.2;
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
    # ---- the Kalshi live multipliers card stays on screen when Kalshi's price is late (window change, slow reply)
    pg.click("#simBtn"); pg.wait_for_timeout(6000)
    cards = pg.evaluate("""()=>{
      const s0=Object.assign({},lastS,{sim:false,quote:null});sim=false;const sym=s0.selected,wE=s0.tick-s0.elapsed+WINDOW,now=Date.now()/1000;
      const base={sym,tk:"X",yes_bid:0.89,yes_ask:0.90,no_bid:0.10,no_ask:0.11,last:0.9};
      const show=q=>{if(q)quoteBy[sym]=Object.assign({},base,q);else delete quoteBy[sym];render(s0);
        const c=[...document.querySelectorAll('#cards .card')].filter(x=>x.innerText.toLowerCase().includes('kalshi live multipliers'));
        return c.length?c[0].innerText.replace(/\\n+/g,' | ').toLowerCase():null};
      return {fresh:show({close:wE,ts:now}),old10:show({close:wE,ts:now-10}),old30:show({close:wE,ts:now-30}),
              prev:show({close:wE-900,ts:now-2}),none:show(null)}}""")
    ok(cards["fresh"] and "up 1.11x" in cards["fresh"] and "down 9.09x" in cards["fresh"] and "from" not in cards["fresh"], "a fresh Kalshi price shows UP and DOWN multipliers: %s" % cards["fresh"])
    ok(cards["old10"] and "up 1.11x" in cards["old10"] and "price from 10 s ago" in cards["old10"], "a 10 s old price still shows, with its age: %s" % cards["old10"])
    ok(cards["old30"] and "waiting for kalshi's price" in cards["old30"] and "1.11x" not in cards["old30"], "a price older than 20 s is not shown as live: %s" % cards["old30"])
    ok(cards["prev"] and "waiting for kalshi to open this window" in cards["prev"] and "1.11x" not in cards["prev"], "the last window's price is never shown for the new window: %s" % cards["prev"])
    ok(cards["none"] and "waiting for kalshi's price" in cards["none"], "with no price at all the card still shows, saying it is waiting: %s" % cards["none"])
    # ---- a new window's market is fetched by name right away (Kalshi's open-markets list only shows it ~28 s after it opens)
    bn = pg.evaluate("""async()=>{
      sim=false;const out={},real_get=kalshiGet;
      const mk=(tk,end,o)=>Object.assign({ticker:tk,close_time:new Date(end*1000).toISOString(),status:"active",floor_strike:"60000.5",yes_bid_dollars:"0.5000",yes_ask_dollars:"0.5200",no_bid_dollars:"0.4800",no_ask_dollars:"0.5000",last_price_dollars:"0.5100"},o||{});
      const run=async(label,ago,byName,listOf)=>{const sym="BTC",end=Date.now()/1000+900-ago,calls=[];delete quoteBy[sym];delete strike[sym];
        kalshiGet=async p=>{calls.push(p.startsWith("/markets/")?"by-name":"list");if(p.startsWith("/markets/")){const r=byName(p,end);if(r instanceof Error)throw r;return r}return {markets:listOf(end)}};
        let err=null;try{await refreshMarket(sym,end,true)}catch(e){err=e.message}
        const q=quoteBy[sym];out[label]={calls:calls.join("+"),err,got:!!q&&Math.abs(q.close-end)<=5,strike:strike[sym]&&strike[sym].v||null}};
      const prevOnly=end=>[mk("OLD",end-900)],both=end=>[mk("OLD",end-900),mk("NEW",end)];
      byNameOff.BTC=0;
      await run("a",10,(p,end)=>p==="/markets/"+windowTicker("BTC",end)?{market:mk(windowTicker("BTC",end),end)}:new Error("HTTP 404"),prevOnly);
      await run("b",2,(p,end)=>({market:mk(windowTicker("BTC",end),end,{status:"initialized",floor_strike:null})}),prevOnly);
      byNameOff.BTC=0;await run("c",10,()=>new Error("HTTP 404 not found"),both);await run("c2",11,()=>({market:null}),both);
      byNameOff.BTC=0;await run("d",100,()=>{throw new Error("by-name must not be used")},both);
      await run("e",10,()=>new Error("HTTP 429 too many requests"),prevOnly);
      out.ex=windowTicker("BTC",1795649400)+" "+windowTicker("ETH",Date.UTC(2026,10,26,5,0)/1000)+" "+windowTicker("SOL",Date.UTC(2026,2,8,7,15)/1000);
      kalshiGet=real_get;return out}""")
    ok(bn["a"] == {"calls": "by-name", "err": None, "got": True, "strike": 60000.5}, "10 s into a window the new market is found by name, with its strike, even though the list lacks it: %s" % bn["a"])
    ok(bn["b"]["calls"] == "by-name+list" and not bn["b"]["got"] and bn["b"]["err"] is None, "a market that is not open yet (no strike) is not used: %s" % bn["b"])
    ok(bn["c"]["calls"] == "by-name+list" and bn["c"]["got"] and bn["c2"]["calls"] == "list", "a failed by-name fetch falls back to the list and is not retried for a minute: %s / %s" % (bn["c"], bn["c2"]))
    ok(bn["d"]["calls"] == "list" and bn["d"]["got"], "after 45 s into the window only the list is used: %s" % bn["d"])
    ok(bn["e"]["err"] and "429" in bn["e"]["err"], "'too many requests' still reaches the slow-down handling: %s" % bn["e"])
    ok(bn["ex"] == "KXBTC15M-26NOV251830-30 KXETH15M-26NOV260000-00 KXSOL15M-26MAR080315-15", "market names are built in New York time, midnight and the March clock change included: %s" % bn["ex"])
    # ---- early selling of real Auto bets (rules, guards, accounting); every Kalshi call is faked, nothing real is sent
    SELLJS = """async()=>{
  sim=false;refreshBook=()=>{};const out={},TK="KXBTC15M-26NOV251830-30",now=()=>Date.now()/1000;let posts=[];
  // the page's own once-a-second work must not touch these checks while they run (it re-reads prices and calls these two itself), so only this test calls them
  const _rsw=realSellWatch,_acw=autoCashWatch,_ar=acctRefresh;realSellWatch=()=>{};autoCashWatch=()=>{};acctRefresh=async()=>{};      // acctRefresh would reload the order list (and wipe the faked one) after each sale
  apost=async(p,o)=>{posts.push([p,o]);return window.__ans||{ok:true,filled:true,fill_count:10,net:4.9,left:0}};
  const ord=(o)=>Object.assign({filled:true,src:"auto",env:"prod",order_id:"o1",ticker:TK,sym:"BTC",side:"yes",fill_count:10,cost_total:6.2,w:now()+300,t:now()-100},o||{});
  const setup=(o)=>{acct.info={env:"prod",ready:true,trading:true,selling:true,build:HELPER_EXPECT};acct.stale=false;acct.sum={ok:true,balance:100};acct.orders=[ord(o)];
    for(const k in sellSt)delete sellSt[k];sellRules={f65:true,m10:true};sellMin=0;posts=[];window.__ans=null};
  const book=(side,bid,age)=>bid==null?null:(side==="no"?{tk:TK,ts:now()-(age||0),ok:true,no:bid*100+2,yes:(1-bid)*100}:{tk:TK,ts:now()-(age||0),ok:true,yes:bid*100+2,no:(1-bid)*100});
  const go=async(label,o,pCal,bid,mod,age,lag)=>{setup(o);if(mod)mod();const tick=Math.floor(now()),side=(o&&o.side)||"yes";res.BTC={pCal,tick};delete bookBy.BTC;const bk=book(side,bid,age);if(bk)bookBy.BTC=bk;
    quoteBy.BTC=lag||{tk:TK,ts:now(),yes_bid:0.55,yes_ask:0.57,no_bid:0.43,no_ask:0.45};
    _rsw(tick);await new Promise(r=>setTimeout(r,60));out[label]=posts.map(p=>({url:p[0],side:p[1].side,min:p[1].min_price,rule:p[1].rule,ps:p[1].ps}))};
  await go("flip_yes",null,0.30,0.55);
  await go("market10_yes",null,0.80,0.93);
  await go("no_rule_just_below_m10",null,0.84,0.93);
  await go("model_agrees_no_sale",null,0.90,0.93);
  await go("selling_off",null,0.30,0.55,()=>{acct.info.selling=false});
  await go("stale_book",null,0.30,0.55,null,5);
  await go("no_book_yet",null,0.30,null);
  await go("lagging_listed_quote_high_live_book_low",{side:"no"},0.56,0.40,null,0,{tk:TK,ts:now(),yes_bid:0.07,yes_ask:0.10,no_bid:0.90,no_ask:0.93});
  await go("last_10_seconds",{w:now()+8},0.30,0.55);
  await go("dust_bid",null,0.30,0.04);
  await go("no_rules_ticked",null,0.30,0.55,()=>{sellRules={}});
  await go("already_sold_row",{closed:true,sold_count:10,sold_net:4.9},0.30,0.55);
  await go("settled_row",{res:"no"},0.30,0.55);
  await go("not_auto_row",{src:"manual"},0.30,0.55);
  await go("stale_helper",null,0.30,0.55,()=>{acct.stale=true});
  await go("live_book_high_listed_quote_low",null,0.30,0.55,null,0,{tk:TK,ts:now(),yes_bid:0.05,yes_ask:0.07,no_bid:0.93,no_ask:0.95});
  await go("flip_no",{side:"no"},0.70,0.50);
  await go("min_bid_holds_low_sale",null,0.30,0.55,()=>{sellMin=75});
  await go("min_bid_allows_high_sale",null,0.80,0.93,()=>{sellMin=75});
  await go("min_bid_equal_allows",null,0.80,0.93,()=>{sellMin=93});
  // throttle: the same market is not hit twice within 2 s, and an unclear answer is never repeated
  // the page recalculates res.BTC every second, so the faked price and book are put back right before each call
  const fix=()=>{res.BTC={pCal:0.3,tick:Math.floor(now())};bookBy.BTC={tk:TK,ts:now(),ok:true,yes:57,no:45}};
  setup();fix();
  window.__ans={ok:true,filled:false};let t=Math.floor(now());_rsw(t);await new Promise(r=>setTimeout(r,40));fix();_rsw(t);await new Promise(r=>setTimeout(r,40));out.throttle_posts=posts.length;
  sellSt[TK].last-=3;window.__ans={ok:true,filled:false};fix();_rsw(t);await new Promise(r=>setTimeout(r,40));out.after_2s_posts=posts.length;
  setup();apost=async()=>{throw new Error("timeout")};fix();
  _rsw(t);await new Promise(r=>setTimeout(r,40));sellSt[TK].last-=3;fix();_rsw(t);await new Promise(r=>setTimeout(r,40));out.unclear_answer_done=sellSt[TK].done;
  // the fake-money cash-out test reads the same live order book; the table from before is kept aside
  refreshBook=()=>{};autoSt.cs={n:3,f65:{ex:1}};delete autoSt.csV;const fb={sym:"BTC",side:"UP",tk:TK,stake:10,mult:1.1};pendAuto=[fb];res.BTC={pCal:0.30,tick:t};
  bookBy.BTC={tk:TK,ts:now(),ok:true,yes:57,no:45};quoteBy.BTC={tk:TK,ts:now(),yes_bid:0.97,yes_ask:0.98,no_bid:0.02,no_ask:0.03};_acw(t,100);
  out.shadow_bid=fb.co&&fb.co.f65&&fb.co.f65.bid;out.shadow_old_table_kept=JSON.stringify(autoSt.cs0)===JSON.stringify({n:3,f65:{ex:1}})&&autoSt.cs===null&&autoSt.csV===2;pendAuto=[];
  // accounting
  liveRes[TK]="no";
  const full=ord({closed:true,sold_count:10,sold_net:4.9,res:"no"}),part=ord({sold_count:4,sold_net:2.0}),plain=ord({}),win=ord({res:"yes"});
  const oc=r=>{const x=outcome(r);return {won:x.won,net:x.net==null?null:Math.round(x.net*100)/100,pay:x.pay==null?null:Math.round(x.pay*100)/100}};
  out.sold_all_loss=oc(full);out.part_sold_lost_rest=oc(Object.assign({},part,{}));liveRes[TK]="yes";out.part_sold_won_rest=oc(part);out.unsold_won=oc(win);
  delete liveRes[TK];out.part_sold_waiting=oc(part);out.unsold_waiting=oc(plain);out.sold_all_profit=oc(ord({closed:true,sold_count:10,sold_net:7}));
  liveRes[TK]="yes";out.label_full_won=resTxt(full,false);liveRes[TK]="no";out.label_full_lost=resTxt(ord({closed:true,sold_count:10,sold_net:9}),true);delete liveRes[TK];out.label_full=resTxt(full,false);out.label_part=resTxt(part,true);out.label_plain=resTxt(plain,true);
  realSellWatch=_rsw;autoCashWatch=_acw;acctRefresh=_ar;
  return out}"""
    sv = pg.evaluate(SELLJS)
    one = lambda k: len(sv[k]) == 1 and sv[k][0]["url"] == "/account/sell"
    ok(one("flip_yes") and sv["flip_yes"][0]["side"] == "yes" and sv["flip_yes"][0]["rule"] == "f65" and sv["flip_yes"][0]["min"] == 45, "the model flipping to 70%% the other way sells a YES bet at the bid minus 10c: %s" % sv["flip_yes"])
    ok(one("market10_yes") and sv["market10_yes"][0]["rule"] == "m10", "a bid 10 points above the model's win chance sells it: %s" % sv["market10_yes"])
    ok(one("flip_no") and sv["flip_no"][0]["side"] == "no" and sv["flip_no"][0]["min"] == 40, "a NO bet is sold the same way, from the NO bid: %s" % sv["flip_no"])
    ok(sv["min_bid_holds_low_sale"] == [] and one("min_bid_allows_high_sale") and one("min_bid_equal_allows"), "with a minimum bid of 75c a sale at a 55c bid is held, and one at 93c still goes (also when the minimum equals the bid): %s %s" % (sv["min_bid_holds_low_sale"], sv["min_bid_allows_high_sale"]))
    mb = pg.evaluate("""()=>{const el=$("sellMin"),o={};const set=v=>{el.value=v;el.dispatchEvent(new Event("change"))};
      set("80");o.a=[sellMin,el.value,ls.get("k15sellmin",null)];set("150");o.b=[sellMin,el.value];set("abc");o.c=[sellMin,el.value];set("-5");o.d=sellMin;set("0");o.e=sellMin;return o}""")
    ok(mb["a"] == [80, "80", 80] and mb["b"] == [99, "99"] and mb["c"] == [0, "0"] and mb["d"] == 0 and mb["e"] == 0, "the minimum-bid box keeps what is typed (0-99 cents, anything else becomes 0 or 99) and remembers it: %s" % mb)
    ok(all(sv[k] == [] for k in ("no_rule_just_below_m10", "model_agrees_no_sale")), "no rule firing means no sale")
    ok(all(sv[k] == [] for k in ("selling_off", "stale_book", "no_book_yet", "last_10_seconds", "dust_bid", "no_rules_ticked", "already_sold_row", "settled_row", "not_auto_row", "stale_helper")),
       "nothing is sold when selling is off, the order-book price is stale or missing, under 10 s are left, the bid is dust, no rule is ticked, the bet is sold/settled/not Auto, or the helper is old")
    ok(sv["lagging_listed_quote_high_live_book_low"] == [] and one("live_book_high_listed_quote_low"), "sales are judged from the live order book, not the listed quote that lags by many seconds (the 19:28 HYPE case: listed bid 90c, real bid 40c, no sale)")
    ok(sv["shadow_bid"] == 0.55 and sv["shadow_old_table_kept"] is True, "the fake cash-out test also reads the live order book, and the table built from the lagging quote is kept aside: %s" % [sv["shadow_bid"], sv["shadow_old_table_kept"]])
    ok(sv["throttle_posts"] == 1 and sv["after_2s_posts"] == 2, "the same bet is not hit twice within 2 s, and is tried again after 2 s: %s then %s" % (sv["throttle_posts"], sv["after_2s_posts"]))
    ok(sv["unclear_answer_done"] is True, "when the answer to a sale is unclear it is never repeated")
    ok(sv["sold_all_loss"] == {"won": False, "net": -1.3, "pay": 4.9} and sv["sold_all_profit"]["won"] is True and sv["sold_all_profit"]["net"] == 0.8, "a bet sold in full is judged by the money it brought back: %s" % sv["sold_all_loss"])
    ok(sv["part_sold_won_rest"] == {"won": True, "net": 1.8, "pay": 8} and sv["part_sold_lost_rest"]["net"] == -4.2 and sv["part_sold_waiting"]["won"] is None, "a part-sold bet pays the sale plus only the contracts still held: %s" % sv["part_sold_won_rest"])
    ok(sv["unsold_won"] == {"won": True, "net": 3.8, "pay": 10} and sv["unsold_waiting"]["won"] is None, "a bet that was never sold is accounted exactly as before")
    ok((sv["label_full_won"], sv["label_full_lost"], sv["label_full"], sv["label_part"], sv["label_plain"]) == ("Sold early: loss · would have won if held", "Sold early: profit · would have lost if held", "Sold early: loss · market not settled yet", "Part sold: Won", "Won"),
       "a bet sold early shows its money result and how it would have ended if held: %s" % [sv["label_full_won"], sv["label_full_lost"], sv["label_full"]])
    # ---- the real bet history shows only bets that went through (attempts that didn't are still kept in the helper's log)
    hh = pg.evaluate("""()=>{const T="KXBTC15M-H",mk=(f,o)=>Object.assign({filled:f,src:"auto",env:"prod",ticker:T+Math.random(),sym:"BTC",side:"yes",cost_total:5,fill_count:8,time:"t",price_cents:60,count:8,order_id:f?"o":null,refused:f?null:"insufficient balance"},o||{});
      liveRes[T]="yes";acct.info={env:"prod",ready:true,trading:true};acct.sum={ok:true,balance:100};acct.orders=[mk(true,{ticker:T}),mk(true,{ticker:T}),mk(false),mk(false)];rhSrc="auto";$("rhw").style.display="block";renderRH();
      return {rows:document.querySelectorAll("#rhTbl tr").length-1,refusal:$("rhTbl").innerText.includes("insufficient"),sum:$("rhSum").innerText,kept:acct.orders.length}}""")
    ok(hh["rows"] == 2 and not hh["refusal"] and "not filled" not in hh["sum"] and hh["kept"] == 4 and "+$6.00" in hh["sum"], "the real bet history hides bets that didn't go through and its totals are unchanged: %s" % hh)
    # ---- bet history layout and the sale status (UP/DOWN, time left when bought, 12-hour times, a Selling column; the Auto card shows tries too)
    H2 = """()=>{const T="KXHYPE15M-26NOV251930-30",t0=1795652897;
  acct.info={env:"prod",ready:true,trading:true,selling:true};acct.sum={ok:true,balance:100};
  acct.orders=[{filled:true,src:"auto",env:"prod",ticker:T,sym:"HYPE",side:"no",cost_total:21.03,fill_count:22.48,time:"2026-11-25 19:28:17",t:t0,w:1795653000,price_cents:99,count:22,order_id:"o9"},
   {filled:true,src:"auto",env:"prod",ticker:"KXDOGE15M-X",sym:"DOGE",side:"yes",cost_total:12.34,fill_count:15,time:"2026-11-25 18:26:56",t:t0-3600,w:t0-3600+95,price_cents:85,count:15,order_id:"o8",closed:true,sold_count:15,sold_net:9.5},
   {filled:true,src:"auto",env:"prod",ticker:"KXBTC15M-Z",sym:"BTC",side:"yes",cost_total:5,fill_count:8,time:"x",t:t0-7200,w:t0-7200+400,price_cents:60,count:8,order_id:"o7"}];
  liveRes[T]="no";
  acct.sells=[{ticker:T,side:"no",env:"prod",t:t0+3,rule:"m10",filled:false,refused:"The bid is now 40¢, below the 88¢ minimum for this sale, so nothing was sold."},{ticker:T,side:"no",env:"prod",t:t0+6,rule:"m10",filled:false,refused:"The bid is now 54¢, below the 88¢ minimum for this sale, so nothing was sold."},
              {ticker:"KXDOGE15M-X",side:"yes",env:"prod",t:t0-3500,rule:"f65",filled:true,fill_count:15,net:9.5}];
  rhSrc="auto";$("rhw").style.display="block";renderRH();
  const head=[...document.querySelectorAll("#rhTbl tr:first-child th")].map(x=>x.innerText),rows=[...document.querySelectorAll("#rhTbl tr")].slice(1).map(r=>[...r.cells].map(c=>c.innerText));
  // the status line
  winStart=winStart||0;const o=acct.orders[0];sellStatus(o,"tried to sell early (Market +10 pts), not sold: The bid is now 54¢, below the 88¢ minimum for this sale; still held");acct.bud={auto:{'*':{bank:227.89,avail:222,open:0,net:0,w:0,l:0,peak:230,since:1}}};real.auto=true;renderRealAuto();
  return {head,rows,status:$("arStats").innerText.replace(/\\\\n+/g," | ")}}"""
    hv = pg.evaluate(H2)
    ok([x.upper() for x in hv["head"]] == ["WINDOW END", "COIN", "SIDE", "TIME LEFT WHEN BOUGHT", "CONTRACTS", "AVG PAID", "MULTIPLIER", "RESULT", "SELLING", "COST", "PAYOUT", "NET"], "the bet history columns: no Limit column, a time-left column and a Selling column: %s" % hv["head"])
    r0, r1, r2 = hv["rows"]
    ok((r0[2], r1[2], r2[2]) == ("DOWN", "UP", "UP"), "sides read UP / DOWN instead of YES / NO")
    ok(re.match(r"^[A-Z][a-z]{2} \d+, \d+:\d\d (AM|PM)$", r0[0]) is not None and r0[0].endswith("7:30 PM"), "each real bet shows the end time of the window it was bought in, on a 12-hour clock: %s" % r0[0])
    FH = """()=>{const sv=avRows;avRows=[{w:1795653000,sym:"HYPE",side:"DOWN",p:0.97,lb:0.95,tau:103,tgt:30,mult:1/0.9,stake:20,pnl:2.22,bank:500,up:false,split:false,res:"WIN"},
      {w:1795652100,sym:"BTC",side:"UP",p:0.95,lb:0.93,tau:95,tgt:1,mult:1.25,stake:10,pnl:-10,bank:480,up:false,split:true,res:"LOSS"},{w:1795653900,sym:"ETH",side:"UP",p:0.96,lb:0.94,tau:200,tgt:1,mult:1.1,stake:5,pnl:null,bank:null,up:null,split:false,res:"OPEN"}];
      $("avCoin").innerHTML='<option value="">All coins</option>';$("avRes").value="";$("avMin").value="0";renderAutoHistory();
      const head=[...document.querySelectorAll("#avTbl tr:first-child th")].map(x=>x.innerText),rows=[...document.querySelectorAll("#avTbl tr")].slice(1).map(r=>[...r.cells].map(c=>c.innerText));avRows=sv;return {head,rows}}"""
    fh = pg.evaluate(FH)
    ok([x.upper() for x in fh["head"]] == [x.upper() for x in hv["head"]], "the fake bet history has the same columns as the real one: %s" % fh["head"])
    f0, f1, f2 = fh["rows"]
    ok(f0 == [r0[0], "HYPE", "DOWN", "1:43", "22.22", "90\u00a2", "\u00d71.11", "Won", "\u2013", "$20.00", "$22.22", "+$2.22"] and f1[7] == "Lost" and f1[10] == "$0.00" and f1[9].endswith("(split)") and f2[7] == "Waiting" and f2[11] == "\u2013",
       "fake rows read like real ones: window, UP/DOWN, time left, contracts, price paid, multiplier, Won/Lost/Waiting, cost, payout, net: %s" % f0)
    ok((r0[3], r1[3], r2[3]) == ("1:43", "1:35", "6:40"), "time left in the window when each bet was bought (m:ss): %s" % [r0[3], r1[3], r2[3]])
    ok(r0[8].startswith("Tried 2") and "not sold" in r0[8] and "54" in r0[8] and r1[8].startswith("Sold 15.00 for $9.50") and r2[8] == "–", "the Selling column shows tries with the reason, sales with the cash back, or a dash: %s / %s" % (r0[8], r1[8]))
    ok("tried to sell early" in hv["status"] and "HYPE DOWN" in hv["status"], "the real Auto card's status line shows a try to sell")
    # ---- Auto prices a bet from the live order book; the listed price (which lags) is not needed and is never used on its own
    AB = """async()=>{
  sim=false;const out={},now=()=>Date.now()/1000,_rsw=realSellWatch,_acw=autoCashWatch,_rb=refreshBook,_rm=refreshMarket,_hb=hBase,_ra=real.auto;
  realSellWatch=()=>{};autoCashWatch=()=>{};let rb=[];refreshBook=(s,t)=>rb.push(t);refreshMarket=async()=>{};real.auto=false;
  const wEnd=Math.floor(now())+120,wStart=wEnd-900,TK=windowTicker("BTC",wEnd);
  const run=(label,o)=>{o=o||{};rb=[];pendAuto=[];autoDone=false;autoG=0;autoNote="";hBase=o.nohelper?null:"http://x";
    for(const s of syms)if(s!=="BTC")delete res[s];
    const tick=Math.floor(now());res.BTC={pCal:0.97,tick,tau:120,anchorLn:11,asrc:"kalshi"};autoStab.BTC={side:"UP",n:9,t:tick-1};
    delete quoteBy.BTC;if(o.q)quoteBy.BTC=Object.assign({tk:TK,close:wEnd,yes_ask:0.80,yes_bid:0.78,no_ask:0.22,no_bid:0.20},o.q);
    delete bookBy.BTC;if(o.bk)bookBy.BTC=Object.assign({tk:TK,ts:now(),ok:true,yes:90,no:12},o.bk);
    autoStep(tick,120,wStart,wEnd);
    out[label]={bets:pendAuto.map(b=>({tk:b.tk,mult:Math.round(b.mult*1000)/1000,ask:b.ask,bid:b.bid})),book_reads:rb.length,note:autoNote}};
  run("stale_listed_fresh_book",{q:{ts:now()-60},bk:{}});
  run("no_listed_fresh_book",{bk:{}});
  run("fresh_listed_no_book",{q:{ts:now()},bk:null});
  run("fresh_listed_book_unreadable",{q:{ts:now()},bk:{ok:false}});
  run("book_nothing_for_sale",{q:{ts:now()},bk:{yes:null}});
  run("no_helper_fresh_listed",{nohelper:true,q:{ts:now()}});
  run("no_helper_stale_listed",{nohelper:true,q:{ts:now()-60}});
  pendAuto=[];autoDone=false;
  // lvPlan for an Auto bet: the order book only
  hBase="http://x";acct.sum={ok:true,balance:100};rb=[];
  bookBy.BTC={tk:TK,ts:now(),ok:true,yes:90,no:12};quoteBy.BTC={tk:TK,close:wEnd,ts:now()-60,yes_ask:0.50,yes_bid:0.48,no_ask:0.52,no_bid:0.50};
  const p1=lvPlan("BTC","UP",20,{cushion:3,max:96,tk:TK,end:wEnd});out.lv_book={ticker:p1.ticker,ask:p1.ask,price:p1.price,err:p1.err||null};
  bookBy.BTC.ts=now()-5;const p2=lvPlan("BTC","UP",20,{cushion:3,max:96,tk:TK,end:wEnd});out.lv_stale_book={err:p2.err,reads:rb.length};
  bookBy.BTC={tk:TK,ts:now(),ok:true,yes:97,no:4};const p3=lvPlan("BTC","UP",20,{cushion:3,max:96,tk:TK,end:wEnd});out.lv_book_too_dear=p3.err;
  quoteBy.BTC.ts=now();const p4=lvPlan("BTC","UP",20,{cushion:3});out.lv_click_listed={ticker:p4.ticker,ask:p4.ask};
  realSellWatch=_rsw;autoCashWatch=_acw;refreshBook=_rb;refreshMarket=_rm;hBase=_hb;real.auto=_ra;delete res.BTC;delete bookBy.BTC;delete quoteBy.BTC;autoDone=false;pendAuto=[];
  return out}"""
    ab = pg.evaluate(AB)
    ok(len(ab["stale_listed_fresh_book"]["bets"]) == 1 and ab["stale_listed_fresh_book"]["bets"][0]["ask"] == 0.9 and len(ab["no_listed_fresh_book"]["bets"]) == 1,
       "Auto bets from a fresh order book even when the listed price is a minute old or missing, at the book's price: %s" % ab["stale_listed_fresh_book"])
    ok(ab["no_listed_fresh_book"]["bets"][0]["tk"] == ab["stale_listed_fresh_book"]["bets"][0]["tk"], "without a listed price the market is found by its name")
    ok(ab["fresh_listed_no_book"]["bets"] == [] and ab["fresh_listed_no_book"]["book_reads"] == 1 and ab["fresh_listed_book_unreadable"]["bets"] == [] and ab["book_nothing_for_sale"]["bets"] == [],
       "a fresh listed price alone never places an Auto bet: no order book means it reads one and waits, an unreadable or empty book means no bet")
    ok(len(ab["no_helper_fresh_listed"]["bets"]) == 1 and ab["no_helper_stale_listed"]["bets"] == [], "with no helper running (fake money only) the fresh listed price is still used, and a stale one is not")
    ok(ab["lv_book"] == {"ticker": ab["lv_book"]["ticker"], "ask": 90, "price": 93, "err": None} and ab["lv_click_listed"]["ask"] == 50, "a real Auto order is sized from the order book (90c), not the listed 50c; a manual click still uses the listed quote: %s" % ab["lv_book"])
    ok(ab["lv_stale_book"]["err"].endswith("stale") and ab["lv_stale_book"]["reads"] == 1 and "above the 96" in ab["lv_book_too_dear"], "a stale book refreshes and retries instead of falling back; a book price above what the bet is worth is refused")
    # ---- exit log: each Auto position's path (model, live book, listed quote) and a snapshot of every sale, sent to the helper after the result
    EX = """async()=>{
  const out={},now=()=>Date.now()/1000,sv={rb:refreshBook,kg:kalshiGet,hp:hpost,hb:hBase,rsw:realSellWatch,acw:autoCashWatch};
  realSellWatch=()=>{};autoCashWatch=()=>{};refreshBook=()=>{};hBase="http://x";sim=false;kalshiSlowUntil=0;
  for(const k in exitPos)delete exitPos[k];exitQ=[];exitSent=0;exitErr="";
  const end=Math.floor(now())+100,TK=windowTicker("BTC",end),T=Math.floor(now());
  acct.info={env:"prod",ready:true,trading:true,selling:true,build:HELPER_EXPECT};
  acct.orders=[{filled:true,src:"auto",env:"prod",order_id:"o1",ticker:TK,sym:"BTC",side:"yes",fill_count:10,cost_total:9,w:end,t:T-30}];
  pendAuto=[{w:end-900,sym:"BTC",side:"UP",tk:TK,rk:end+"|BTC|UP",tau:130,stake:9,mult:1/0.9}];
  const put=(p,yb)=>{res.BTC={pCal:p,pRaw:p+0.01,tick:T,P:60000.5,tau:100,an:{sigma:0.0005},q:[59900,59950,60000,60060,60100]};bookBy.BTC={tk:TK,ts:now(),ok:true,yes:100-(100-yb)+2,no:100-yb};quoteBy.BTC={tk:TK,ts:now()-12,yes_bid:0.95,no_bid:0.04,yes_ask:0.96,no_ask:0.05,close:end}};
  put(0.90,94);res.BTC.tick=T-30;exitWatch(T-30);put(0.85,93);res.BTC.tick=T-15;exitWatch(T-15);put(0.80,93);exitWatch(T);exitWatch(T);
  const e=exitPos["real|o1"],f=exitPos["fake|"+end+"|BTC|UP"];
  out.rows=e&&e.rows.length;out.row=e&&e.rows[2];out.fake_rows=f&&f.rows.length;out.fake_entry=f&&Math.round(f.entry*1000)/1000;
  const x=exitSale("real|o1","m10",0.80,0.93);out.snap=x;
  // after the sale the bid goes up to 97c, then the window closes
  put(0.95,97);res.BTC.tick=Math.floor(now())+1;exitWatch(Math.floor(now())+1);
  for(const k in exitPos)exitPos[k].end=now()-3;
  let posted=null;hpost=async(p,o)=>{posted=[p,o.rows.length];return {ok:true,added:o.rows.length}};exitBusy=false;
  let asks=0;kalshiGet=async p=>{asks++;return {market:{ticker:TK,result:"yes",expiration_value:"60010.25",floor_strike:60000}}};
  exitClose(now());await new Promise(r=>setTimeout(r,30));exitClose(now());
  out.queued=exitQ.length;out.asks=asks;const q=exitQ.find(r=>r.key==="real|o1");
  out.final=q&&{res:q.res,won:q.won,settle_value:q.settle_value,strike:q.strike,max_after:q.sales[0].max_bid_after,contracts:q.contracts};
  await new Promise(r=>setTimeout(r,30));
  out.posted=posted;out.after_flush={q:exitQ.length,sent:exitSent};
  // an old helper (no /data/exits): the positions stay queued and the note says why
  exitQ=[{key:"k1"}];hpost=async()=>{throw new Error("HTTP 404")};exitLastFlush=0;exitBusy=false;exitFlush(now());await new Promise(r=>setTimeout(r,30));out.old_helper={q:exitQ.length,err:exitErr};
  // nothing is recorded in a practice run
  for(const k in exitPos)delete exitPos[k];sim=true;exitWatch(T);out.sim_rows=Object.keys(exitPos).length;sim=false;
  // the fake cash-out test leaves a snapshot when a rule fires
  pendAuto=[{w:end-900,sym:"BTC",side:"UP",tk:TK,rk:end+"|BTC|UP",tau:130,stake:9,mult:1/0.9}];for(const k in exitPos)delete exitPos[k];for(const k in exitPos)exitPos[k].end=end;
  Object.assign(pendAuto[0],{end});res.BTC={pCal:0.30,tick:T};bookBy.BTC={tk:TK,ts:now(),ok:true,yes:57,no:45};sv.acw(T,100);
  const fe=exitPos["fake|"+end+"|BTC|UP"];out.fake_snap_rules=fe?fe.sales.map(s=>s.rule).sort().join(","):null;
  realSellWatch=sv.rsw;autoCashWatch=sv.acw;refreshBook=sv.rb;kalshiGet=sv.kg;hpost=sv.hp;hBase=sv.hb;pendAuto=[];acct.orders=[];exitQ=[];exitSent=0;exitErr="";for(const k in exitPos)delete exitPos[k];delete res.BTC;delete bookBy.BTC;delete quoteBy.BTC;
  return out}"""
    ex = pg.evaluate(EX)
    ok(ex["rows"] == 3 and ex["fake_rows"] == 3 and ex["row"][2] == 0.8 and ex["row"][4] == 93 and ex["row"][5] == 5 and ex["row"][7] == 0.95 and len(ex["row"]) == 15 and ex["row"][11] == 0.0005 and abs(ex["row"][12] - 55 / 60000.5) < 1e-6 and ex["row"][13] is not None and ex["fake_entry"] == 0.9, "every second of a real and a fake Auto position is recorded once (model chance, live bids, listed quote, volatility, model range and uncertainty): %s" % ex["row"])
    sn = ex["snap"]
    ok(sn and sn["model"] == 0.8 and sn["bid"] == 0.93 and sn["gap"] == 0.125 and sn["left"] >= 98 and sn["upnl_per"] == 0.025 and sn["upnl"] == 0.254 and sn["move15"] == -0.05 and sn["move30"] == -0.1,
       "a sale's snapshot has the model chance, the market price, the gap, time left, unrealized P&L and how the model moved: %s" % sn)
    ok(ex["final"] == {"res": "yes", "won": True, "settle_value": 60010.25, "strike": 60000, "max_after": 0.97, "contracts": 10} and ex["queued"] == 2, "after the close it adds the highest bid after the sale and Kalshi's result and settlement value: %s" % ex["final"])
    ok(ex["posted"] == ["/data/exits", 2] and ex["after_flush"] == {"q": 0, "sent": 2}, "finished positions go to the helper's exit log: %s" % ex["posted"])
    ok(ex["old_helper"]["q"] == 1 and "updated helper" in ex["old_helper"]["err"], "with the old helper they wait in the browser and the note says why")
    ok(ex["sim_rows"] == 0 and ex["fake_snap_rules"] == "f55,f65,m05,m10", "nothing is recorded in a practice run; the fake cash-out test leaves a snapshot for each rule that fires: %s" % ex["fake_snap_rules"])
    # ---- skip log: every 2 s while Auto looks, each coin at 70%+ with the first check that stopped it; saved after Kalshi's results, never shown
    SK = """async()=>{
  const out={},now=()=>Date.now()/1000,sv={rb:refreshBook,kg:kalshiGet,hp:hpost,hb:hBase,learn:autoSt.learn};
  hBase="http://x";sim=false;kalshiSlowUntil=0;autoSt.learn={};skipW=null;skipDone=[];skipQ=[];for(const k in skipRead)delete skipRead[k];
  let reads=[];refreshBook=(s,t)=>reads.push(s);
  const wEnd=Math.floor(now()/900)*900+900,wStart=wEnd-900,T=Math.floor(now()/2)*2,TK=windowTicker("BTC",wEnd);
  for(const s of syms)delete res[s];
  res.BTC={pCal:0.97,tick:T,tau:120,asrc:"kalshi"};res.ETH={pCal:0.15,tick:T,tau:120,asrc:"kalshi"};res.DOGE={pCal:0.75,tick:T,tau:120,asrc:"kalshi"};res.SOL={pCal:0.55,tick:T,tau:120,asrc:"kalshi"};
  autoStab.BTC={side:"UP",n:9,t:T};autoStab.ETH={side:"DOWN",n:9,t:T};
  bookBy.BTC={tk:TK,ts:now(),ok:true,yes:90,no:12};delete bookBy.ETH;
  pendAuto=[{w:wStart,sym:"BTC",side:"UP",tau:120,edge:0.05,lb:0.95,mult:1/0.906,stake:10,tk:TK,rk:wEnd+"|BTC|UP",rw:0}];
  autoNote="Best so far: BTC UP";
  skipWatch(T,120,wStart,wEnd);skipWatch(T,120,wStart,wEnd);skipWatch(T+1,119,wStart,wEnd);
  const w=skipW;out.rows=w.rows.map(x=>[x[2],x[3],x[4],x[5],x[7],x[13]]);out.reads=reads.slice();out.bets=w.bets.map(b=>b.sym+" "+b.side);out.notes=w.notes.length;out.btc=w.rows.find(x=>x[2]==="BTC");
  skipWatch(T+2,300,wStart,wEnd);out.too_early=w.rows.length;      // more than 4:00 left: nothing recorded
  // the window ends: the record waits for Kalshi's result for each coin, then goes to the helper
  w.end=now()-3;let asks=[];kalshiGet=async p=>{asks.push(p);return {market:{result:p.includes("BTC")?"yes":"no",expiration_value:"1.5",floor_strike:1}}};
  let posted=null;hpost=async(p,o)=>{posted=[p,o.rows.length,o.rows[0]];return {ok:true}};
  skipWatch(T+4,890,wStart+900,wEnd+900);
  for(let i=0;i<4;i++){skipDone.forEach(x=>x.lastAsk=0);skipClose(now());await new Promise(r=>setTimeout(r,20))}
  skipLastFlush=0;skipClose(now());await new Promise(r=>setTimeout(r,20));
  out.asks=asks.length;out.posted=posted&&{path:posted[0],n:posted[1],res:posted[2].res,coins:posted[2].coins,bets:posted[2].bets.length,key:posted[2].key.startsWith("skip|")};out.queue_after=skipQ.length;
  // practice runs record nothing
  skipW=null;sim=true;skipWatch(T,120,wStart,wEnd);out.sim=skipW===null;sim=false;
  refreshBook=sv.rb;kalshiGet=sv.kg;hpost=sv.hp;hBase=sv.hb;autoSt.learn=sv.learn;skipW=null;skipDone=[];skipQ=[];pendAuto=[];for(const s of ["BTC","ETH","DOGE","SOL"]){delete res[s];delete autoStab[s];delete bookBy[s]}
  return out}"""
    sk = pg.evaluate(SK)
    ok(sk["rows"] == [["BTC", 1, 0.97, 1, 90, "ok"], ["ETH", 0, 0.85, 0, None, "band"], ["DOGE", 1, 0.75, 0, None, "band"]] and sk["btc"][11] == 0.906,
       "each coin at 70 percent or more is recorded once per 2 s with its confidence, band, live ask, cost, edge and the check that stopped it (coins under 70 percent are left out): %s" % sk["rows"])
    ok(sk["reads"] == ["ETH"] and sk["bets"] == ["BTC UP"] and sk["too_early"] == 3, "an 80 percent coin with no order-book price gets one read; Auto's bet is kept; nothing is recorded with more than 4:00 left")
    ok(sk["posted"] and sk["posted"]["path"] == "/data/skips" and sk["posted"]["res"]["BTC"]["res"] == "yes" and sk["posted"]["coins"] == ["BTC", "ETH", "DOGE"] and sk["queue_after"] == 0,
       "after the close each coin gets Kalshi's result and the window goes to the helper's skip log: %s" % sk["posted"])
    ok(sk["sim"] is True, "nothing is recorded in a practice run")
    # ---- the real early-selling table on the bet history: only real fills, only ticked rules, judged on Kalshi's result
    ST = """()=>{
  const sv={s:acct.sells,i:acct.info,r:Object.assign({},liveRes),rules:sellRules,src:rhSrc};
  acct.info=Object.assign({},acct.info||{},{env:"prod"});sellRules={f65:true,m10:true};
  liveRes["T1"]="no";liveRes["T2"]="yes";liveRes["T3"]="yes";delete liveRes["T4"];
  acct.sells=[
    {env:"prod",src:"auto",rule:"m10",filled:true,fill_count:10,net:9.2,gross:9.3,ticker:"T1",side:"yes",buy_oid:"b1"},      // loser saved: +9.20
    {env:"prod",src:"auto",rule:"m10",filled:true,fill_count:5,net:4.7,gross:4.75,ticker:"T2",side:"yes",buy_oid:"b2"},      // winner sold in two parts: 4.70+4.60-10 = -0.70
    {env:"prod",src:"auto",rule:"m10",filled:true,fill_count:5,net:4.6,gross:4.65,ticker:"T2",side:"yes",buy_oid:"b2"},
    {env:"prod",src:"auto",rule:"f65",filled:true,fill_count:8,net:2.4,gross:2.45,ticker:"T3",side:"yes",buy_oid:"b3"},      // flip sold a winner cheap: 2.40-8 = -5.60
    {env:"prod",src:"auto",rule:"m10",filled:true,fill_count:4,net:3.6,gross:3.62,ticker:"T4",side:"no",buy_oid:"b4"},       // market not settled yet
    {env:"prod",src:"auto",rule:"m10",filled:false,fill_count:0,ticker:"T1",side:"yes",buy_oid:"b1"},                       // a try that didn't fill: not a sale
    {env:"prod",src:"auto",rule:"m05",filled:true,fill_count:3,net:2.8,ticker:"T1",side:"yes",buy_oid:"b9"},                 // a rule that is off now
    {env:"demo",src:"auto",rule:"m10",filled:true,fill_count:3,net:2.8,ticker:"T1",side:"yes",buy_oid:"b8"}];               // the other account
  const st=sellStats();rhSrc="auto";renderRHSell();
  const out={S:st.S,off:st.off,rows:[...document.querySelectorAll("#rhSellTbl tr")].map(tr=>[...tr.children].map(td=>td.textContent)),txt:$("rhSellTxt").textContent,shown:$("rhSell").style.display};
  sellRules={};renderRHSell();out.none=$("rhSellTxt").textContent;
  acct.sells=sv.s;acct.info=sv.i;for(const k in liveRes)delete liveRes[k];Object.assign(liveRes,sv.r);sellRules=sv.rules;rhSrc=sv.src;renderRHSell();
  return out}"""
    st = pg.evaluate(ST)
    rows = {r[0]: r for r in st["rows"][1:]}
    ok(rows["Market +10 pts"] == ["Market +10 pts", "3", "1", "+$9.20", "1", "-$0.70", "93\u00a2", "+$8.50", "1"] and rows["Flip 65%+"][1:] == ["1", "0", "\u2013", "1", "-$5.60", "31\u00a2", "-$5.60", "0"],
       "per ticked rule: bets sold, losers saved and winners sold (a sale in two parts counts once), money per bet, price sold at, net vs holding, unsettled: %s" % st["rows"][1:])
    ok(len(st["rows"]) == 3 and st["off"] == 1 and "not counted" in st["txt"] and st["shown"] == "block", "a try that didn't fill, the other account and a rule that is off now are left out")
    ok("No early-selling rule is ticked" in st["none"], "with no rule ticked the table says so")
    # ---- nothing for sale: that coin is dropped and Auto looks for another one in the same window
    pg.evaluate("()=>{if(window.__rm)realMirror=window.__rm}")      # an earlier check stands in for realMirror
    NS = """async()=>{
  const out={},now=()=>Date.now()/1000,sv={ap:apost,ai:acct.info,rb:refreshBook,ra:real.auto,hb:hBase,ar:acctRefresh,learn:autoSt.learn,bank:autoSt.bank,peak:autoSt.peak};
  sim=false;hBase="http://x";refreshBook=()=>{};acctRefresh=async()=>{};acct.info=Object.assign({},acct.info||{},{ready:true,trading:true,env:"prod",build:HELPER_EXPECT});real.auto=false;
  const wEnd=Math.floor(now())+120,wS=wEnd-900,TK=s=>windowTicker(s,wEnd);
  winStart=wS;
  // a. how a refusal is classified
  bookBy.BTC={tk:TK("BTC"),ts:now(),ok:true,yes:90,no:12};acct.sum={ok:true,balance:500};
  const ask=async ans=>{apost=async()=>ans;return realMirror("auto","BTC","UP",20,{w:wEnd,p:0.97,tk:TK("BTC")})};
  out.zero_fill=await ask({ok:true,filled:false,fill_count:0});
  out.nothing=await ask({ok:false,error:"Nothing is for sale at 93¢ or better right now, so nothing was bought."});
  out.resting=await ask({ok:false,error:"Kalshi returned HTTP 409: fill or kill insufficient resting volume"});
  out.price=await ask({ok:false,error:"The price is now 95¢, above the 93¢ this bet is worth, so it wasn't placed."});
  bookBy.BTC={tk:TK("BTC"),ts:now(),ok:true,yes:null,no:12};out.empty_book=await realMirror("auto","BTC","UP",20,{w:wEnd,p:0.97,tk:TK("BTC")});
  // b. the coin is dropped and Auto picks another one in the same window
  autoSt.learn={};autoSt.bank=1000;autoSt.peak=1000;autoNS={w:0,s:new Set()};
  for(const s of syms)delete res[s];
  const T=Math.floor(now());
  res.BTC={pCal:0.99,tick:T,tau:120,anchorLn:11,asrc:"kalshi"};res.ETH={pCal:0.03,tick:T,tau:120,anchorLn:7,asrc:"kalshi"};
  autoStab.BTC={side:"UP",n:9,t:T-1};autoStab.ETH={side:"DOWN",n:9,t:T-1};
  bookBy.BTC={tk:TK("BTC"),ts:now(),ok:true,yes:90,no:12};bookBy.ETH={tk:TK("ETH"),ts:now(),ok:true,yes:16,no:85};
  pendAuto=[{w:wS,sym:"BTC",side:"UP",rk:wEnd+"|BTC|UP",stake:10,mult:1.1,tk:TK("BTC")}];autoDone=true;
  autoNoSale("BTC","UP",wS,wEnd);
  out.after_drop={pend:pendAuto.length,done:autoDone,note:autoNote,excl:[...autoNS.s]};
  autoStep(T,120,wS,wEnd);
  out.new_pick=pendAuto.map(b=>b.sym+" "+b.side);out.stamp=pendAuto.map(b=>[b.conf,b.mk,b.bp,b.be]);
  // c. with the window's other bet still standing, nothing new is picked
  pendAuto=[{w:wS,sym:"ETH",side:"DOWN",rk:wEnd+"|ETH|DOWN",stake:10,mult:1.1},{w:wS,sym:"SOL",side:"UP",rk:wEnd+"|SOL|UP",stake:10,mult:1.1}];autoDone=true;
  autoNoSale("SOL","UP",wS,wEnd);out.other_leg={pend:pendAuto.map(b=>b.sym),done:autoDone};
  // d. too late in the window
  pendAuto=[{w:wS,sym:"ETH",side:"DOWN",rk:wEnd+"|ETH|DOWN",stake:10,mult:1.1}];autoDone=true;
  autoNoSale("ETH","DOWN",wS,now()+20);out.too_late={pend:pendAuto.length,done:autoDone};
  apost=sv.ap;acct.info=sv.ai;refreshBook=sv.rb;real.auto=sv.ra;hBase=sv.hb;acctRefresh=sv.ar;autoSt.learn=sv.learn;autoSt.bank=sv.bank;autoSt.peak=sv.peak;
  pendAuto=[];autoDone=false;autoNS={w:0,s:new Set()};for(const s of ["BTC","ETH"]){delete res[s];delete autoStab[s];delete bookBy[s]}
  return out}"""
    ns = pg.evaluate(NS)
    ok([ns[k] for k in ("zero_fill", "nothing", "resting", "empty_book")] == ["nosale"] * 4 and ns["price"] == "retry",
       "no contracts at the price (unfilled, nothing for sale, not enough resting, empty book) stops that coin; a price above what the bet is worth still retries: %s" % ns)
    ok(ns["after_drop"]["pend"] == 0 and ns["after_drop"]["done"] is False and ns["after_drop"]["excl"] == ["BTC"] and ns["new_pick"] == ["ETH DOWN"],
       "the coin's fake bet is dropped and Auto picks another coin that passes every check, never the dropped one: %s" % ns["new_pick"])
    ok(ns["stamp"] == [[0.97, 0.85, 0.892, 0.033]], "each fake Auto bet is stamped with the market's chance, the blended chance and its edge: %s" % ns["stamp"])
    ok(ns["other_leg"] == {"pend": ["ETH"], "done": True} and ns["too_late"] == {"pend": 1, "done": True}, "no new pick while the window's other bet stands, or under 25 s left")
    # ---- market-blend test (shadow only): books what "only bet when the blended chance beats the price" would have kept and dropped
    BL = """()=>{
  const sv=autoSt.bl,out={};autoSt.bl={};
  // a bet the blend keeps (market agrees) and one it drops (market far below the model)
  blBook({be:0.03,conf:0.97,bp:0.95,mk:0.94,hit:true,stake:10,pnl:0.5,px:"real"});
  blBook({be:-0.06,conf:0.95,bp:0.87,mk:0.83,hit:false,stake:10,pnl:-10});
  blBook({be:null,conf:0.95,hit:true,stake:10,pnl:1});      // no market price recorded: not counted
  const a=autoSt.bl.all;out.n=a.n;out.b0=a.b0;out.b2=a.b2;out.real=autoSt.bl.real.n;
  renderBl();out.html=$("autoBl").textContent;
  autoSt.bl=sv;renderBl();return out}"""
    bl = pg.evaluate(BL)
    ok(bl["n"] == 2 and bl["real"] == 1 and bl["b0"] == {"kn": 1, "kw": 1, "ks": 10, "kp": 0.5, "dn": 1, "dw": 0, "ds": 10, "dp": -10} and "model 96.0%, market 88.5%, blended 91.0%" in bl["html"],
       "the market-blend table keeps the bet whose blended chance beats the price and drops the other; bets with no market price are left out: %s" % bl["b0"])
    # ---- the signal popup shows only a fired signal, as it was when it fired
    SF = """()=>{const base=Object.assign({},lastS),sel=base.selected,out={},w=1795800000;dismissed.clear();
  const rows=()=>[...document.querySelectorAll('#sig .sigrow.up,#sig .sigrow.dn')].filter(e=>!e.classList.contains('leaving')).map(e=>e.textContent.replace(/\s+/g," ").trim());
  const live={w,sym:sel,side:"UP",p:0.93,tau:200,final:1,lo:1,hi:1,target:1,price:1};
  render(Object.assign({},base,{signals:[live],fired:[]}));out.above_not_fired=rows();
  render(Object.assign({},base,{signals:[live],fired:[{w,sym:sel,side:"UP",p:0.912,tau:205}]}));out.fired=rows();
  render(Object.assign({},base,{signals:[],fired:[{w,sym:sel,side:"UP",p:0.912,tau:205}]}));out.after_drop=rows();
  render(Object.assign({},base,{signals:[live],fired:[{w,sym:"ZZZ",side:"UP",p:0.95,tau:100}]}));out.other_coin=rows();
  dismissed.add(w+"|"+sel+"|UP");render(Object.assign({},base,{signals:[live],fired:[{w,sym:sel,side:"UP",p:0.912,tau:205}]}));out.closed=rows();
  dismissed.clear();render(base);return out}"""
    sf = pg.evaluate(SF)
    ok(sf["above_not_fired"] == [] and len(sf["fired"]) == 1 and "fired with 03:25 left" in sf["fired"][0] and "91.2%" in sf["fired"][0] and sf["after_drop"] == sf["fired"],
       "no popup for a coin that is above the threshold but hasn't fired; a fired one shows its time and confidence at firing and stays when the live confidence drops: %s" % sf["fired"])
    ok(sf["other_coin"] == [] and sf["closed"] == [], "another coin's signal and a closed one don't show")
    # ---- a new best pick notification replaces the old one
    pk = pg.evaluate("""()=>{const mk=T=>({w:77,T,tau:T,min:0.9,top:null,more:[],closest:null});const cnt=()=>[...document.querySelectorAll('#sig .sigrow.pick')].filter(e=>!e.classList.contains('leaving')).map(e=>e.innerText);
      const base=Object.assign({},lastS),o={};render(Object.assign({},base,{picks:[mk(300)]}));o.a=cnt();render(Object.assign({},base,{picks:[mk(300),mk(180)]}));o.b=cnt();render(Object.assign({},base,{picks:[mk(300),mk(180),mk(60)]}));o.c=cnt();return o}""")
    ok(len(pk["a"]) == 1 and len(pk["b"]) == 1 and len(pk["c"]) == 1 and "03:00" in pk["b"][0] and "01:00" in pk["c"][0], "a new best pick notification replaces the old one (1, 1, 1 on screen, always the newest): %s" % [len(pk["a"]), len(pk["b"]), len(pk["c"])])
    # closing the newest pick (X, or Switch to, which does the same dismissal) must not bring the older one back; a newer pick still shows
    pc = pg.evaluate("""()=>{const mk=T=>({w:77,T,tau:T,min:0.9,top:null,more:[],closest:null});const cnt=()=>[...document.querySelectorAll('#sig .sigrow.pick')].filter(e=>!e.classList.contains('leaving')).length;
      const base=Object.assign({},lastS),o={};dismissed.clear();render(Object.assign({},base,{picks:[mk(300),mk(180)]}));o.before=cnt();
      dismissed.add("pick|77|180");render(Object.assign({},base,{picks:[mk(300),mk(180)]}));o.after_close=cnt();render(Object.assign({},base,{picks:[mk(300),mk(180)]}));o.again=cnt();
      render(Object.assign({},base,{picks:[mk(300),mk(180),mk(60)]}));o.newer=cnt();dismissed.clear();return o}""")
    ok(pc == {"before": 1, "after_close": 0, "again": 0, "newer": 1}, "closing the newest best pick does not bring the older one back, and a newer pick still appears: %s" % pc)
    ok(not errs, "no script errors during the checks: %s" % errs[:1])
    b.close()

print("\n%d failed" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
