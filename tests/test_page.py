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
  apost=async(p,o)=>{posts.push([p,o]);return window.__ans||{ok:true,filled:true,fill_count:10,net:4.9,left:0}};
  const ord=(o)=>Object.assign({filled:true,src:"auto",env:"prod",order_id:"o1",ticker:TK,sym:"BTC",side:"yes",fill_count:10,cost_total:6.2,w:now()+300,t:now()-100},o||{});
  const setup=(o)=>{acct.info={env:"prod",ready:true,trading:true,selling:true,build:HELPER_EXPECT};acct.stale=false;acct.sum={ok:true,balance:100};acct.orders=[ord(o)];
    for(const k in sellSt)delete sellSt[k];sellRules={f65:true,m10:true};posts=[];window.__ans=null};
  const book=(side,bid,age)=>bid==null?null:(side==="no"?{tk:TK,ts:now()-(age||0),ok:true,no:bid*100+2,yes:(1-bid)*100}:{tk:TK,ts:now()-(age||0),ok:true,yes:bid*100+2,no:(1-bid)*100});
  const go=async(label,o,pCal,bid,mod,age,lag)=>{setup(o);if(mod)mod();const tick=Math.floor(now()),side=(o&&o.side)||"yes";res.BTC={pCal,tick};delete bookBy.BTC;const bk=book(side,bid,age);if(bk)bookBy.BTC=bk;
    quoteBy.BTC=lag||{tk:TK,ts:now(),yes_bid:0.55,yes_ask:0.57,no_bid:0.43,no_ask:0.45};
    realSellWatch(tick);await new Promise(r=>setTimeout(r,60));out[label]=posts.map(p=>({url:p[0],side:p[1].side,min:p[1].min_price,rule:p[1].rule,ps:p[1].ps}))};
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
  // throttle: the same market is not hit twice within 2 s, and an unclear answer is never repeated
  setup();res.BTC={pCal:0.3,tick:Math.floor(now())};bookBy.BTC={tk:TK,ts:now(),ok:true,yes:57,no:45};
  window.__ans={ok:true,filled:false};let t=Math.floor(now());realSellWatch(t);await new Promise(r=>setTimeout(r,40));realSellWatch(t);await new Promise(r=>setTimeout(r,40));out.throttle_posts=posts.length;
  sellSt[TK].last-=3;window.__ans={ok:true,filled:false};realSellWatch(t);await new Promise(r=>setTimeout(r,40));out.after_2s_posts=posts.length;
  setup();apost=async()=>{throw new Error("timeout")};res.BTC={pCal:0.3,tick:t};bookBy.BTC={tk:TK,ts:now(),ok:true,yes:57,no:45};
  realSellWatch(t);await new Promise(r=>setTimeout(r,40));sellSt[TK].last-=3;realSellWatch(t);await new Promise(r=>setTimeout(r,40));out.unclear_answer_done=sellSt[TK].done;
  // the fake-money cash-out test reads the same live order book; the table from before is kept aside
  refreshBook=()=>{};autoSt.cs={n:3,f65:{ex:1}};delete autoSt.csV;const fb={sym:"BTC",side:"UP",tk:TK,stake:10,mult:1.1};pendAuto=[fb];res.BTC={pCal:0.30,tick:t};
  bookBy.BTC={tk:TK,ts:now(),ok:true,yes:57,no:45};quoteBy.BTC={tk:TK,ts:now(),yes_bid:0.97,yes_ask:0.98,no_bid:0.02,no_ask:0.03};autoCashWatch(t,100);
  out.shadow_bid=fb.co&&fb.co.f65&&fb.co.f65.bid;out.shadow_old_table_kept=JSON.stringify(autoSt.cs0)===JSON.stringify({n:3,f65:{ex:1}})&&autoSt.cs===null&&autoSt.csV===2;pendAuto=[];
  // accounting
  liveRes[TK]="no";
  const full=ord({closed:true,sold_count:10,sold_net:4.9,res:"no"}),part=ord({sold_count:4,sold_net:2.0}),plain=ord({}),win=ord({res:"yes"});
  const oc=r=>{const x=outcome(r);return {won:x.won,net:x.net==null?null:Math.round(x.net*100)/100,pay:x.pay==null?null:Math.round(x.pay*100)/100}};
  out.sold_all_loss=oc(full);out.part_sold_lost_rest=oc(Object.assign({},part,{}));liveRes[TK]="yes";out.part_sold_won_rest=oc(part);out.unsold_won=oc(win);
  delete liveRes[TK];out.part_sold_waiting=oc(part);out.unsold_waiting=oc(plain);out.sold_all_profit=oc(ord({closed:true,sold_count:10,sold_net:7}));
  out.label_full=resTxt(full,false);out.label_part=resTxt(part,true);out.label_plain=resTxt(plain,true);
  return out}"""
    sv = pg.evaluate(SELLJS)
    one = lambda k: len(sv[k]) == 1 and sv[k][0]["url"] == "/account/sell"
    ok(one("flip_yes") and sv["flip_yes"][0]["side"] == "yes" and sv["flip_yes"][0]["rule"] == "f65" and sv["flip_yes"][0]["min"] == 45, "the model flipping to 70%% the other way sells a YES bet at the bid minus 10c: %s" % sv["flip_yes"])
    ok(one("market10_yes") and sv["market10_yes"][0]["rule"] == "m10", "a bid 10 points above the model's win chance sells it: %s" % sv["market10_yes"])
    ok(one("flip_no") and sv["flip_no"][0]["side"] == "no" and sv["flip_no"][0]["min"] == 40, "a NO bet is sold the same way, from the NO bid: %s" % sv["flip_no"])
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
    ok((sv["label_full"], sv["label_part"], sv["label_plain"]) == ("Sold early: Lost", "Part sold: Won", "Won"), "the bet history says which bets were sold early: %s" % [sv["label_full"], sv["label_part"], sv["label_plain"]])
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
    ok([x.upper() for x in hv["head"]] == ["TIME", "COIN", "SIDE", "TIME LEFT WHEN BOUGHT", "CONTRACTS", "AVG PAID", "MULTIPLIER", "RESULT", "SELLING", "COST", "PAYOUT", "NET"], "the bet history columns: no Limit column, a time-left column and a Selling column: %s" % hv["head"])
    r0, r1, r2 = hv["rows"]
    ok((r0[2], r1[2], r2[2]) == ("DOWN", "UP", "UP"), "sides read UP / DOWN instead of YES / NO")
    ok(re.search(r"\d:\d\d:\d\d (AM|PM)$", r0[0]) is not None, "times are on a 12-hour clock: %s" % r0[0])
    ok((r0[3], r1[3], r2[3]) == ("1:43", "1:35", "6:40"), "time left in the window when each bet was bought (m:ss): %s" % [r0[3], r1[3], r2[3]])
    ok(r0[8].startswith("Tried 2") and "not sold" in r0[8] and "54" in r0[8] and r1[8].startswith("Sold 15.00 for $9.50") and r2[8] == "–", "the Selling column shows tries with the reason, sales with the cash back, or a dash: %s / %s" % (r0[8], r1[8]))
    ok("tried to sell early" in hv["status"] and "HYPE DOWN" in hv["status"], "the real Auto card's status line shows a try to sell")
    ok(not errs, "no script errors during the checks: %s" % errs[:1])
    b.close()

print("\n%d failed" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
