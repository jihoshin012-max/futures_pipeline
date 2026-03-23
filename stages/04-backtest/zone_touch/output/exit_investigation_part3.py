# archetype: zone_touch
"""
Zone Touch Exit Investigation — Part 3 of 3
Section 5: Interaction Effects
Section 6: Head-to-Head Comparison
Final output: combined report + updated CSV
"""
import pandas as pd
import numpy as np
import warnings, sys, io, codecs
warnings.filterwarnings('ignore')

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')

BASE = "c:/Projects/pipeline"
TRADE_PATH = f"{BASE}/stages/04-backtest/zone_touch/output/p2_trade_details.csv"
MERGED_P2A = f"{BASE}/stages/01-data/output/zone_prep/NQ_merged_P2a.csv"
MERGED_P2B = f"{BASE}/stages/01-data/output/zone_prep/NQ_merged_P2b.csv"
BARDATA_PATH = f"{BASE}/stages/01-data/output/zone_prep/NQ_bardata_P2.csv"
INVEST_CSV = f"{BASE}/stages/04-backtest/zone_touch/output/zone_touch_exit_investigation.csv"
PART1_MD = f"{BASE}/stages/04-backtest/zone_touch/output/exit_investigation_part1.md"
PART2_MD = f"{BASE}/stages/04-backtest/zone_touch/output/exit_investigation_part2.md"
REPORT_MD = f"{BASE}/stages/04-backtest/zone_touch/output/exit_investigation_report.md"

TICK_SIZE = 0.25
COST_TICKS = 3

md_buf = io.StringIO()

class Tee:
    def __init__(self, *s):
        self.s = s
    def write(self, d):
        for x in self.s:
            x.write(d)
    def flush(self):
        for x in self.s:
            x.flush()

tee = Tee(sys.stdout, md_buf)

def out(s=""):
    tee.write(s + "\n")

# ── Load ───────────────────────────────────────────────────────────────
print("Loading data...")
trades = pd.read_csv(TRADE_PATH)
invest = pd.read_csv(INVEST_CSV)
touches = pd.concat([pd.read_csv(MERGED_P2A), pd.read_csv(MERGED_P2B)], ignore_index=True)
bardata = pd.read_csv(BARDATA_PATH, low_memory=False)
bardata.columns = [c.strip() for c in bardata.columns]

trades['dt'] = pd.to_datetime(trades['datetime'])
touches['dt'] = pd.to_datetime(touches['DateTime'])

assert len(invest) == 312
print(f"  Invest CSV: {len(invest)} rows, {len(invest.columns)} cols")

# ── Touch join for RotBarIndex ─────────────────────────────────────────
print("Joining for RotBarIndex...")
trades['expected_appdir'] = np.where(trades['direction'] == 'LONG', -1, 1)
tc_keep = ['ZoneWidthTicks','TouchSequence','SourceLabel','ZoneTop','ZoneBot',
           'TouchType','RotBarIndex','CascadeState','Penetration','BarIndex','ApproachDir']

parts = []
for period in ['P2a','P2b']:
    ts = trades[trades['period']==period].copy().sort_values('dt').reset_index(drop=True)
    tc = touches[(touches['Period']==period)&(touches['RotBarIndex']>=0)].copy().sort_values('dt').reset_index(drop=True)
    if len(ts)==0 or len(tc)==0:
        parts.append(ts); continue
    mcols = list(dict.fromkeys(['dt']+tc_keep))
    r = pd.merge_asof(ts, tc[mcols], on='dt', tolerance=pd.Timedelta('5min'),
                      direction='nearest', suffixes=('','_touch'))
    dm = r['ApproachDir'].astype(float) != r['expected_appdir'].astype(float)
    for idx in r[dm].index:
        tdt = r.loc[idx,'dt']; ed = r.loc[idx,'expected_appdir']
        cands = tc[(tc['ApproachDir']==ed)&((tc['dt']-tdt).abs()<pd.Timedelta('5min'))]
        if len(cands)>0:
            b = cands.loc[(cands['dt']-tdt).abs().idxmin()]
            for c in tc_keep: r.loc[idx,c] = b[c]
        else:
            for c in tc_keep: r.loc[idx,c] = np.nan
    parts.append(r)

df = pd.concat(parts, ignore_index=True).sort_values('trade_id').reset_index(drop=True)
df['entry_bar_idx'] = df['RotBarIndex'].apply(lambda x: int(x)+1 if pd.notna(x) and x>=0 else -1)
df['WL'] = np.where(df['pnl_ticks']>0, 'W', 'L')
df['pnl'] = df['pnl_ticks'].astype(float)
df['mae'] = df['mae_ticks'].astype(float)
df['mfe'] = df['mfe_ticks'].astype(float)
print(f"  Matched: {(df['RotBarIndex'].notna()).sum()}/312")

# Merge invest columns we need
for c in ['zone_width','zone_width_ratio','session','crossed_opposite_edge',
          'bars_to_max_penetration','penetration_speed','is_battleground','zone_width_bin',
          'score_margin','touch_sequence','cascade_state','source_label','tf_minutes',
          'pen_speed_10bar','pen_speed_25bar','mfe_at_10bar','mfe_at_20bar','mfe_at_30bar',
          'fills_5t','entry_5t','entry_5t_bar']:
    if c in invest.columns:
        df[c] = invest.set_index('trade_id').loc[df['trade_id'].values, c].values

# ── Bar arrays ─────────────────────────────────────────────────────────
bar_high = bardata['High'].values.astype(float)
bar_low = bardata['Low'].values.astype(float)
bar_close = bardata['Last'].values.astype(float)
bar_open = bardata['Open'].values.astype(float)
n_bars = len(bardata)

# ── Simulation engines ─────────────────────────────────────────────────
def sim_2leg(eb, ep, d, t1, t2, stp, tc, l1=0.67, l2=0.33):
    t1p=t1*TICK_SIZE; t2p=t2*TICK_SIZE; sp=stp*TICK_SIZE
    t1f=False; end=min(eb+tc,n_bars)
    for b in range(eb,end):
        bh=b-eb+1
        if d=='LONG':
            if bar_low[b]<=ep-sp:
                if t1f: return {'et':'T1+STOP','rp':l1*t1+l2*(-stp),'bh':bh,'t1f':True}
                else: return {'et':'STOP','rp':-stp,'bh':bh,'t1f':False}
            fav=bar_high[b]-ep
        else:
            if bar_high[b]>=ep+sp:
                if t1f: return {'et':'T1+STOP','rp':l1*t1+l2*(-stp),'bh':bh,'t1f':True}
                else: return {'et':'STOP','rp':-stp,'bh':bh,'t1f':False}
            fav=ep-bar_low[b]
        if not t1f and fav>=t1p:
            t1f=True
            if fav>=t2p: return {'et':'TARGET','rp':l1*t1+l2*t2,'bh':bh,'t1f':True}
        if t1f and fav>=t2p: return {'et':'TARGET','rp':l1*t1+l2*t2,'bh':bh,'t1f':True}
    if end>eb:
        cp=((bar_close[end-1]-ep) if d=='LONG' else (ep-bar_close[end-1]))/TICK_SIZE
        rp=(l1*t1+l2*cp) if t1f else cp
        return {'et':'TIMECAP','rp':rp,'bh':tc,'t1f':t1f}
    return {'et':'TIMECAP','rp':0,'bh':0,'t1f':False}

def sim_2leg_be(eb, ep, d, t1, t2, stp, tc, be_trig, l1=0.67, l2=0.33):
    t1p=t1*TICK_SIZE; t2p=t2*TICK_SIZE; sp=stp*TICK_SIZE; bp=be_trig*TICK_SIZE
    t1f=False; be_on=False; end=min(eb+tc,n_bars)
    for b in range(eb,end):
        bh=b-eb+1
        if d=='LONG':
            fav=bar_high[b]-ep
            if not be_on and fav>=bp: be_on=True
            csp=ep if be_on else ep-sp
            if bar_low[b]<=csp:
                sl=0 if be_on and csp==ep else -stp
                if t1f: return {'et':'T1+BE' if be_on else 'T1+STOP','rp':l1*t1+l2*sl,'bh':bh,'t1f':True}
                else: return {'et':'BE' if be_on else 'STOP','rp':sl,'bh':bh,'t1f':False}
        else:
            fav=ep-bar_low[b]
            if not be_on and fav>=bp: be_on=True
            csp=ep if be_on else ep+sp
            if bar_high[b]>=csp:
                sl=0 if be_on and csp==ep else -stp
                if t1f: return {'et':'T1+BE' if be_on else 'T1+STOP','rp':l1*t1+l2*sl,'bh':bh,'t1f':True}
                else: return {'et':'BE' if be_on else 'STOP','rp':sl,'bh':bh,'t1f':False}
        if not t1f and fav>=t1p:
            t1f=True
            if fav>=t2p: return {'et':'TARGET','rp':l1*t1+l2*t2,'bh':bh,'t1f':True}
        if t1f and fav>=t2p: return {'et':'TARGET','rp':l1*t1+l2*t2,'bh':bh,'t1f':True}
    if end>eb:
        cp=((bar_close[end-1]-ep) if d=='LONG' else (ep-bar_close[end-1]))/TICK_SIZE
        rp=(l1*t1+l2*cp) if t1f else cp
        return {'et':'TIMECAP','rp':rp,'bh':tc,'t1f':t1f}
    return {'et':'TIMECAP','rp':0,'bh':0,'t1f':False}

def sim_2leg_trail(eb, ep, d, t1, stp, tc, trail, t2cap=None, l1=0.67, l2=0.33):
    t1p=t1*TICK_SIZE; sp=stp*TICK_SIZE; trp=trail*TICK_SIZE
    t2cp=t2cap*TICK_SIZE if t2cap else None
    t1f=False; hw=0; end=min(eb+tc,n_bars)
    for b in range(eb,end):
        bh=b-eb+1
        if d=='LONG':
            fav=bar_high[b]-ep; adv_p=bar_low[b]
        else:
            fav=ep-bar_low[b]; adv_p=bar_high[b]
        if not t1f:
            if d=='LONG':
                if adv_p<=ep-sp: return {'et':'STOP','rp':-stp,'bh':bh,'t1f':False}
            else:
                if adv_p>=ep+sp: return {'et':'STOP','rp':-stp,'bh':bh,'t1f':False}
            if fav>=t1p:
                t1f=True; hw=fav
                if t2cp and fav>=t2cp:
                    return {'et':'TARGET','rp':l1*t1+l2*t2cap,'bh':bh,'t1f':True}
        else:
            if fav>hw: hw=fav
            dd=hw-fav
            if dd>=trp:
                tp_ticks=(hw-trail*TICK_SIZE/TICK_SIZE)  # wrong, fix:
                if d=='LONG':
                    tsp=ep+hw-trp
                    if bar_low[b]<=tsp:
                        pnl_t=(tsp-ep)/TICK_SIZE
                        return {'et':'TRAIL','rp':l1*t1+l2*pnl_t,'bh':bh,'t1f':True}
                else:
                    tsp=ep-hw+trp
                    if bar_high[b]>=tsp:
                        pnl_t=(ep-tsp)/TICK_SIZE
                        return {'et':'TRAIL','rp':l1*t1+l2*pnl_t,'bh':bh,'t1f':True}
            if d=='LONG':
                if adv_p<=ep-sp: return {'et':'T1+STOP','rp':l1*t1+l2*(-stp),'bh':bh,'t1f':True}
            else:
                if adv_p>=ep+sp: return {'et':'T1+STOP','rp':l1*t1+l2*(-stp),'bh':bh,'t1f':True}
            if t2cp and fav>=t2cp:
                return {'et':'TARGET','rp':l1*t1+l2*t2cap,'bh':bh,'t1f':True}
    if end>eb:
        cp=((bar_close[end-1]-ep) if d=='LONG' else (ep-bar_close[end-1]))/TICK_SIZE
        rp=(l1*t1+l2*cp) if t1f else cp
        return {'et':'TIMECAP','rp':rp,'bh':tc,'t1f':t1f}
    return {'et':'TIMECAP','rp':0,'bh':0,'t1f':False}

def sim_2leg_nobounce(eb, ep, d, t1, t2, stp, tc, adv_thr, bounce_thr, bounce_win, l1=0.67, l2=0.33):
    """2-leg with no-bounce early exit: if adverse >= adv_thr and close doesn't bounce bounce_thr within bounce_win bars, exit."""
    t1p=t1*TICK_SIZE; t2p=t2*TICK_SIZE; sp=stp*TICK_SIZE
    t1f=False; end=min(eb+tc,n_bars)
    nb_triggered=False; first_adv_bar=None
    worst_close_adv=0

    for b in range(eb,end):
        bh=b-eb+1
        if d=='LONG':
            if bar_low[b]<=ep-sp:
                if t1f: return {'et':'T1+STOP','rp':l1*t1+l2*(-stp),'bh':bh,'t1f':True}
                else: return {'et':'STOP','rp':-stp,'bh':bh,'t1f':False}
            fav=bar_high[b]-ep
            adv_inst=(ep-bar_low[b])/TICK_SIZE
            close_adv=(ep-bar_close[b])/TICK_SIZE
        else:
            if bar_high[b]>=ep+sp:
                if t1f: return {'et':'T1+STOP','rp':l1*t1+l2*(-stp),'bh':bh,'t1f':True}
                else: return {'et':'STOP','rp':-stp,'bh':bh,'t1f':False}
            fav=ep-bar_low[b]
            adv_inst=(bar_high[b]-ep)/TICK_SIZE
            close_adv=(bar_close[b]-ep)/TICK_SIZE

        # No-bounce check
        if first_adv_bar is None and adv_inst >= adv_thr:
            first_adv_bar = b
            worst_close_adv = max(close_adv, 0)
        if first_adv_bar is not None:
            if close_adv > worst_close_adv:
                worst_close_adv = close_adv
            recovery = worst_close_adv - close_adv
            bars_since = b - first_adv_bar
            if bars_since >= bounce_win and recovery < bounce_thr:
                # No bounce — exit at close
                exit_pnl = -close_adv  # close_adv is adverse in ticks
                if t1f:
                    return {'et':'T1+NOBOUNCE','rp':l1*t1+l2*(-close_adv),'bh':bh,'t1f':True}
                else:
                    return {'et':'NOBOUNCE','rp':-close_adv,'bh':bh,'t1f':False}
            elif recovery >= bounce_thr:
                first_adv_bar = None  # reset — bounced OK
                worst_close_adv = 0

        if not t1f and fav>=t1p:
            t1f=True
            if fav>=t2p: return {'et':'TARGET','rp':l1*t1+l2*t2,'bh':bh,'t1f':True}
        if t1f and fav>=t2p: return {'et':'TARGET','rp':l1*t1+l2*t2,'bh':bh,'t1f':True}

    if end>eb:
        cp=((bar_close[end-1]-ep) if d=='LONG' else (ep-bar_close[end-1]))/TICK_SIZE
        rp=(l1*t1+l2*cp) if t1f else cp
        return {'et':'TIMECAP','rp':rp,'bh':tc,'t1f':t1f}
    return {'et':'TIMECAP','rp':0,'bh':0,'t1f':False}

def sim_2leg_opp_edge(eb, ep, d, t1, t2, stp, tc, zone_top, zone_bot, depth_extra, l1=0.67, l2=0.33):
    """2-leg with opposite edge exit."""
    t1p=t1*TICK_SIZE; t2p=t2*TICK_SIZE; sp=stp*TICK_SIZE
    t1f=False; end=min(eb+tc,n_bars)
    if d=='LONG':
        opp_price = zone_bot - depth_extra*TICK_SIZE
    else:
        opp_price = zone_top + depth_extra*TICK_SIZE

    for b in range(eb,end):
        bh=b-eb+1
        if d=='LONG':
            if bar_low[b]<=ep-sp:
                if t1f: return {'et':'T1+STOP','rp':l1*t1+l2*(-stp),'bh':bh,'t1f':True}
                else: return {'et':'STOP','rp':-stp,'bh':bh,'t1f':False}
            # Opp edge check
            if bar_low[b]<=opp_price:
                pnl_t=(opp_price-ep)/TICK_SIZE
                if t1f: return {'et':'T1+OPEDGE','rp':l1*t1+l2*pnl_t,'bh':bh,'t1f':True}
                else: return {'et':'OPEDGE','rp':pnl_t,'bh':bh,'t1f':False}
            fav=bar_high[b]-ep
        else:
            if bar_high[b]>=ep+sp:
                if t1f: return {'et':'T1+STOP','rp':l1*t1+l2*(-stp),'bh':bh,'t1f':True}
                else: return {'et':'STOP','rp':-stp,'bh':bh,'t1f':False}
            if bar_high[b]>=opp_price:
                pnl_t=(ep-opp_price)/TICK_SIZE
                if t1f: return {'et':'T1+OPEDGE','rp':l1*t1+l2*pnl_t,'bh':bh,'t1f':True}
                else: return {'et':'OPEDGE','rp':pnl_t,'bh':bh,'t1f':False}
            fav=ep-bar_low[b]

        if not t1f and fav>=t1p:
            t1f=True
            if fav>=t2p: return {'et':'TARGET','rp':l1*t1+l2*t2,'bh':bh,'t1f':True}
        if t1f and fav>=t2p: return {'et':'TARGET','rp':l1*t1+l2*t2,'bh':bh,'t1f':True}

    if end>eb:
        cp=((bar_close[end-1]-ep) if d=='LONG' else (ep-bar_close[end-1]))/TICK_SIZE
        rp=(l1*t1+l2*cp) if t1f else cp
        return {'et':'TIMECAP','rp':rp,'bh':tc,'t1f':t1f}
    return {'et':'TIMECAP','rp':0,'bh':0,'t1f':False}


# ── Run a strategy across all trades ───────────────────────────────────
def run_strategy(sim_func, use_5t=False, per_trade_args_fn=None):
    """Run sim_func for all valid trades. Returns DataFrame with net_pnl, trade_id, trend_label.
    per_trade_args_fn(row) returns kwargs dict for sim_func beyond eb, ep, d."""
    results = []
    for i in range(len(df)):
        trend = df.loc[i, 'trend_label']
        direction = df.loc[i, 'direction']

        if use_5t and trend == 'CT':
            if not df.loc[i, 'fills_5t']:
                continue
            eb = int(df.loc[i, 'entry_5t_bar'])
            ep = df.loc[i, 'entry_5t']
        else:
            eb = int(df.loc[i, 'entry_bar_idx'])
            ep = df.loc[i, 'entry_price']

        if eb < 0 or eb >= n_bars:
            continue

        kwargs = per_trade_args_fn(df.loc[i]) if per_trade_args_fn else {}
        res = sim_func(eb, ep, direction, **kwargs)
        res['net_pnl'] = res['rp'] - COST_TICKS
        res['trade_id'] = df.loc[i, 'trade_id']
        res['trend_label'] = trend
        res['max_dd'] = -res['rp'] if res['rp'] < 0 else 0  # single-trade worst
        results.append(res)
    return pd.DataFrame(results) if results else pd.DataFrame()


def strat_stats(rdf):
    if len(rdf) == 0:
        return {'n':0,'wr':0,'pf':0,'ev':0,'maxdd':0}
    w = rdf[rdf['net_pnl']>0]; l = rdf[rdf['net_pnl']<=0]
    gw = w['net_pnl'].sum(); gl = l['net_pnl'].abs().sum()
    pf = gw/gl if gl>0 else float('inf')
    wr = len(w)/len(rdf)*100
    ev = rdf['net_pnl'].mean()
    maxdd = rdf[rdf['net_pnl']<0]['net_pnl'].min() if len(l)>0 else 0
    return {'n':len(rdf),'wr':wr,'pf':pf,'ev':ev,'maxdd':abs(maxdd) if maxdd else 0}


# ══════════════════════════════════════════════════════════════════════
# SECTION 5: INTERACTION EFFECTS
# ══════════════════════════════════════════════════════════════════════
out("# Zone Touch Exit Investigation — Part 3 of 3")
out()
out("## SECTION 5: INTERACTION EFFECTS")
out()

# Helper for cross-tab cells
def cell_stats(sub):
    n = len(sub)
    if n == 0:
        return "—"
    w = sub[sub['WL']=='W']
    l = sub[sub['WL']=='L']
    wr = len(w)/n*100
    mp = sub['pnl'].mean()
    gw = w['pnl'].sum(); gl = l['pnl'].abs().sum()
    pf = gw/gl if gl>0 else float('inf')
    flag = " ⚠️" if n < 10 else ""
    return f"n={n}, WR={wr:.0f}%, PnL={mp:.0f}, PF={pf:.1f}{flag}"

# 5A) Score margin × penetration depth
out("### 5A) Score Margin × Penetration Depth (MAE)")
out()
out("| | Pen 0-50t | Pen 50-100t | Pen 100-150t | Pen 150t+ |")
out("|---|---|---|---|---|")

margin_bins = [(0,2,'0-2'),(2,4,'2-4'),(4,6,'4-6'),(6,99,'6+')]
pen_bins = [(0,50,'0-50t'),(50,100,'50-100t'),(100,150,'100-150t'),(150,9999,'150t+')]

for ml,mh,mlabel in margin_bins:
    row = f"| Margin {mlabel}"
    for pl,ph,_ in pen_bins:
        sub = df[(df['score_margin']>=ml)&(df['score_margin']<mh)&(df['mae']>=pl)&(df['mae']<ph)]
        row += f" | {cell_stats(sub)}"
    out(row + " |")

# 5B) Session × outcome
out()
out("### 5B) Session × Outcome")
out()
out("| | RTH | ETH |")
out("|---|---|---|")

for metric in ['Count','WR','Mean PnL','Mean MAE','Mean MFE','PF','Stop rate']:
    row = f"| {metric}"
    for sess in ['RTH','ETH']:
        sub = df[df['session']==sess]
        if metric == 'Count':
            row += f" | {len(sub)}"
        elif metric == 'WR':
            row += f" | {(sub['WL']=='W').mean()*100:.1f}%"
        elif metric == 'Mean PnL':
            row += f" | {sub['pnl'].mean():.1f}"
        elif metric == 'Mean MAE':
            row += f" | {sub['mae'].mean():.1f}"
        elif metric == 'Mean MFE':
            row += f" | {sub['mfe'].mean():.1f}"
        elif metric == 'PF':
            w = sub[sub['pnl']>0]['pnl'].sum()
            l = sub[sub['pnl']<=0]['pnl'].abs().sum()
            row += f" | {w/l:.2f}" if l>0 else " | inf"
        elif metric == 'Stop rate':
            sr = (sub['exit_type']=='STOP').mean()*100
            row += f" | {sr:.1f}%"
    out(row + " |")

# 5C) Touch sequence × penetration
out()
out("### 5C) Touch Sequence × Penetration")
out()
out("| Seq | Count | Mean pen | Median pen | WR | % pen > 100t |")
out("|:---:|:---:|:---:|:---:|:---:|:---:|")

for seq_val, seq_label in [(1,'1'),(2,'2'),(3,'3')]:
    sub = df[df['touch_sequence']==seq_val]
    if len(sub)==0: continue
    out(f"| {seq_label} | {len(sub)} | {sub['mae'].mean():.0f} | {sub['mae'].median():.0f} | {(sub['WL']=='W').mean()*100:.0f}% | {(sub['mae']>100).mean()*100:.0f}% |")

sub4 = df[df['touch_sequence']>=4]
if len(sub4)>0:
    out(f"| 4+ | {len(sub4)} | {sub4['mae'].mean():.0f} | {sub4['mae'].median():.0f} | {(sub4['WL']=='W').mean()*100:.0f}% | {(sub4['mae']>100).mean()*100:.0f}% |")

# 5D) Cascade state × outcome
out()
out("### 5D) Cascade State × Outcome")
out()
out("| State | Count | WR | Mean PnL | Mean MAE | Stop rate |")
out("|---|:---:|:---:|:---:|:---:|:---:|")

for st in ['NO_PRIOR','PRIOR_HELD','PRIOR_BROKE']:
    sub = df[df['cascade_state']==st]
    if len(sub)==0: continue
    sr = (sub['exit_type']=='STOP').mean()*100
    out(f"| {st} | {len(sub)} | {(sub['WL']=='W').mean()*100:.0f}% | {sub['pnl'].mean():.1f} | {sub['mae'].mean():.0f} | {sr:.0f}% |")

# 5E) Timeframe × penetration × outcome
out()
out("### 5E) Timeframe × Penetration × Outcome")
out()
out("| TF | Count | Mean pen | WR | PF | Stop rate |")
out("|:---:|:---:|:---:|:---:|:---:|:---:|")

for tf in [15,30,60,90,120,240,360,480,720]:
    sub = df[df['tf_minutes']==tf]
    if len(sub)==0: continue
    w=sub[sub['pnl']>0]['pnl'].sum(); l=sub[sub['pnl']<=0]['pnl'].abs().sum()
    pf = w/l if l>0 else float('inf')
    sr = (sub['exit_type']=='STOP').mean()*100
    flag = " ⚠️" if len(sub)<10 else ""
    out(f"| {tf}m | {len(sub)}{flag} | {sub['mae'].mean():.0f} | {(sub['WL']=='W').mean()*100:.0f}% | {pf:.2f} | {sr:.0f}% |")

# 5F) Zone width × outcome (FIXED vs ZONE-REL)
out()
out("### 5F) Zone Width × Outcome (Fixed vs Zone-Relative)")
out()

# Compute zone-relative PnL per trade
print("Computing per-trade zone-relative PnL...")
pnl_zone_rel = np.full(len(df), np.nan)

for i in range(len(df)):
    eb = int(df.loc[i,'entry_bar_idx'])
    if eb < 0 or eb >= n_bars: continue
    ep = df.loc[i,'entry_price']
    d = df.loc[i,'direction']
    zw = df.loc[i,'ZoneWidthTicks']
    if pd.isna(zw) or zw <= 0: continue
    res = sim_2leg(eb, ep, d, 0.5*zw, 1.0*zw, 1.5*zw, 160)
    pnl_zone_rel[i] = res['rp'] - COST_TICKS

df['pnl_zone_rel'] = pnl_zone_rel

out("| Zone width | Count | WR | Mean PnL (fixed) | Mean PnL (zone-rel) | PF (fixed) | PF (zone-rel) | Stop rate |")
out("|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")

zw_bins = [(0,50,'0-50t'),(50,100,'50-100t'),(100,150,'100-150t'),(150,200,'150-200t'),(200,9999,'200t+')]
for lo,hi,label in zw_bins:
    sub = df[(df['zone_width']>=lo)&(df['zone_width']<hi)]
    if len(sub)==0: continue
    n=len(sub)
    wr=(sub['WL']=='W').mean()*100
    mp_f=sub['pnl'].mean()
    mp_z=sub['pnl_zone_rel'].mean()
    wf=sub[sub['pnl']>0]['pnl'].sum(); lf=sub[sub['pnl']<=0]['pnl'].abs().sum()
    pf_f=wf/lf if lf>0 else float('inf')
    wz=sub[sub['pnl_zone_rel']>0]['pnl_zone_rel'].sum()
    lz=sub[sub['pnl_zone_rel']<=0]['pnl_zone_rel'].abs().sum()
    pf_z=wz/lz if lz>0 else float('inf')
    sr=(sub['exit_type']=='STOP').mean()*100
    flag=" ⚠️" if n<10 else ""
    out(f"| {label}{flag} | {n} | {wr:.0f}% | {mp_f:.1f} | {mp_z:.1f} | {pf_f:.2f} | {pf_z:.2f} | {sr:.0f}% |")

# 5G) Zone width × penetration speed
out()
out("### 5G) Zone Width × Penetration Speed (Winners vs Losers)")
out()
out("| Zone width | Mean pen speed W | Mean pen speed L | Speed ratio (L/W) |")
out("|:---:|:---:|:---:|:---:|")

for lo,hi,label in zw_bins:
    sub = df[(df['zone_width']>=lo)&(df['zone_width']<hi)]
    if len(sub)==0: continue
    w = sub[sub['WL']=='W']['penetration_speed'].dropna()
    l = sub[sub['WL']=='L']['penetration_speed'].dropna()
    wm = w.mean() if len(w)>0 else 0
    lm = l.mean() if len(l)>0 else 0
    ratio = lm/wm if wm>0 else 0
    flag=" ⚠️" if len(l)<3 else ""
    out(f"| {label}{flag} | {wm:.1f} | {lm:.1f} | {ratio:.1f}x |")

# 5H) Mode × zone width × outcome
out()
out("### 5H) Mode × Zone Width × Outcome")
out()
out("| Mode | Zone width | Count | WR | PF | Mean PnL (zone-rel) |")
out("|:---:|:---:|:---:|:---:|:---:|:---:|")

for trend in ['CT','WT']:
    for lo,hi,label in [(0,100,'0-100t'),(100,200,'100-200t'),(200,9999,'200t+')]:
        sub = df[(df['trend_label']==trend)&(df['zone_width']>=lo)&(df['zone_width']<hi)]
        if len(sub)==0: continue
        n=len(sub)
        wr=(sub['WL']=='W').mean()*100
        wz=sub[sub['pnl_zone_rel']>0]['pnl_zone_rel'].sum()
        lz=sub[sub['pnl_zone_rel']<=0]['pnl_zone_rel'].abs().sum()
        pf=wz/lz if lz>0 else float('inf')
        mp=sub['pnl_zone_rel'].mean()
        flag=" ⚠️" if n<10 else ""
        out(f"| {trend} | {label}{flag} | {n} | {wr:.0f}% | {pf:.2f} | {mp:.1f} |")

# ══════════════════════════════════════════════════════════════════════
# SECTION 6: HEAD-TO-HEAD COMPARISON
# ══════════════════════════════════════════════════════════════════════
out()
out("---")
out()
out("## SECTION 6: HEAD-TO-HEAD COMPARISON")
out()
out("All strategies use 2-leg exits (67/33 split). Max DD = worst single-trade loss (ticks).")
out()

ct_mask = df['trend_label']=='CT'
wt_mask = df['trend_label']=='WT'
ct_5t_mask = ct_mask & (df['fills_5t']==True)

def fixed_args(trend):
    if trend=='CT': return {'t1':40,'t2':80,'stp':190,'tc':160}
    else: return {'t1':60,'t2':80,'stp':240,'tc':160}

def zr_args(row):
    zw=row['ZoneWidthTicks']
    if pd.isna(zw) or zw<=0: zw=200  # fallback
    return {'t1':0.5*zw,'t2':1.0*zw,'stp':1.5*zw,'tc':160}

def zr_floor_args(row):
    zw=row['ZoneWidthTicks']
    if pd.isna(zw) or zw<=0: zw=200
    return {'t1':0.5*zw,'t2':1.0*zw,'stp':max(1.5*zw, 120),'tc':160}

# Strategy runner
def run_strat(label, sim_fn, use_5t, args_fn):
    rdf = run_strategy(sim_fn, use_5t=use_5t, per_trade_args_fn=args_fn)
    s = strat_stats(rdf)
    return s, rdf

strategies = {}

# ── FIXED FRAMEWORK ───────────────────────────────────────────────────
out("### FIXED FRAMEWORK")
out()
out("| Strategy | Fills | WR | PF | EV/opp | Max DD |")
out("|----------|:---:|:---:|:---:|:---:|:---:|")

# 1. Current v1.0 (market entry)
def fixed_market_args(row):
    return fixed_args(row['trend_label'])

s, rdf = run_strat("Current v1.0", sim_2leg, False, fixed_market_args)
strategies['fixed_v1'] = s
out(f"| Current v1.0 (market, 190/240, 40-80/60-80) | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 2. 5t limit CT
s, rdf = run_strat("5t limit CT", sim_2leg, True, fixed_market_args)
strategies['fixed_5t'] = s
out(f"| 5t limit CT | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 3. 5t + tighter stop (best from 4A: 40t/150t for CT, 40t/150t for WT)
def fixed_tight_args(row):
    if row['trend_label']=='CT': return {'t1':40,'t2':80,'stp':150,'tc':160}
    else: return {'t1':60,'t2':80,'stp':150,'tc':160}
s, rdf = run_strat("5t + 150t stop", sim_2leg, True, fixed_tight_args)
strategies['fixed_tight'] = s
out(f"| 5t + 150t stop | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 4. 5t + BE step-up (best from 4B: BE=40t CT only)
def fixed_be_args(row):
    t = row['trend_label']
    if t=='CT': return {'t1':40,'t2':80,'stp':190,'tc':160,'be_trig':40}
    else: return {'t1':60,'t2':80,'stp':240,'tc':160,'be_trig':40}
s, rdf = run_strat("5t + BE@40t", sim_2leg_be, True, fixed_be_args)
strategies['fixed_be'] = s
out(f"| 5t + BE@40t | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 5. 5t + trail after T1 (best: trail 30t no cap)
def fixed_trail_args(row):
    if row['trend_label']=='CT': return {'t1':40,'stp':190,'tc':160,'trail':30,'t2cap':None}
    else: return {'t1':60,'stp':240,'tc':160,'trail':30,'t2cap':None}
s, rdf = run_strat("5t + trail 30t no cap", sim_2leg_trail, True, fixed_trail_args)
strategies['fixed_trail'] = s
out(f"| 5t + trail 30t no cap | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 6. 5t + no-bounce exit (best: 75t adv, 25t bounce, 50 bar window)
def fixed_nb_args(row):
    t = row['trend_label']
    if t=='CT': return {'t1':40,'t2':80,'stp':190,'tc':160,'adv_thr':75,'bounce_thr':25,'bounce_win':50}
    else: return {'t1':60,'t2':80,'stp':240,'tc':160,'adv_thr':75,'bounce_thr':25,'bounce_win':50}
s, rdf = run_strat("5t + no-bounce 75/25/50", sim_2leg_nobounce, True, fixed_nb_args)
strategies['fixed_nb'] = s
out(f"| 5t + no-bounce 75/25/50 | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 7. 5t + opp edge exit (+25t)
def fixed_opp_args(row):
    t = row['trend_label']
    zt = row['ZoneTop']; zb = row['ZoneBot']
    if pd.isna(zt): zt = row['entry_price']+1000*TICK_SIZE
    if pd.isna(zb): zb = row['entry_price']-1000*TICK_SIZE
    if t=='CT': return {'t1':40,'t2':80,'stp':190,'tc':160,'zone_top':zt,'zone_bot':zb,'depth_extra':25}
    else: return {'t1':60,'t2':80,'stp':240,'tc':160,'zone_top':zt,'zone_bot':zb,'depth_extra':25}
s, rdf = run_strat("5t + opp edge+25t", sim_2leg_opp_edge, True, fixed_opp_args)
strategies['fixed_opp'] = s
out(f"| 5t + opp edge+25t | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 8. Best fixed combined: 5t + trail 30t no cap + opp edge (layer both)
# Can't easily combine in single sim — use the best single improvement
best_fixed_key = max(['fixed_5t','fixed_tight','fixed_be','fixed_trail','fixed_nb','fixed_opp'],
                     key=lambda k: strategies[k]['ev'])
bf = strategies[best_fixed_key]
out(f"| **Best fixed: {best_fixed_key}** | {bf['n']} | {bf['wr']:.1f}% | {bf['pf']:.2f} | {bf['ev']:.1f} | {bf['maxdd']:.0f} |")

# ── ZONE-RELATIVE FRAMEWORK ──────────────────────────────────────────
out()
out("### ZONE-RELATIVE FRAMEWORK")
out()
out("| Strategy | Fills | WR | PF | EV/opp | Max DD |")
out("|----------|:---:|:---:|:---:|:---:|:---:|")

# 1. Zone-rel baseline (market)
s, rdf = run_strat("ZR baseline", sim_2leg, False, zr_args)
strategies['zr_base'] = s
out(f"| ZR baseline (mkt, 0.5x/1.0x/1.5x) | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 2. ZR + 5t CT
s, rdf = run_strat("ZR + 5t CT", sim_2leg, True, zr_args)
strategies['zr_5t'] = s
out(f"| ZR + 5t CT | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 3. ZR + BE (best: 0.5x zw = T1 level)
def zr_be_args(row):
    zw=row['ZoneWidthTicks']
    if pd.isna(zw) or zw<=0: zw=200
    return {'t1':0.5*zw,'t2':1.0*zw,'stp':1.5*zw,'tc':160,'be_trig':0.5*zw}
s, rdf = run_strat("ZR + BE@0.5x", sim_2leg_be, True, zr_be_args)
strategies['zr_be'] = s
out(f"| ZR + 5t + BE@0.5x zw | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 4. ZR + trail (best: 0.15x no cap)
def zr_trail_args(row):
    zw=row['ZoneWidthTicks']
    if pd.isna(zw) or zw<=0: zw=200
    return {'t1':0.5*zw,'stp':1.5*zw,'tc':160,'trail':0.15*zw,'t2cap':None}
s, rdf = run_strat("ZR + trail 0.15x no cap", sim_2leg_trail, True, zr_trail_args)
strategies['zr_trail'] = s
out(f"| ZR + 5t + trail 0.15x no cap | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 5. ZR + no-bounce
def zr_nb_args(row):
    zw=row['ZoneWidthTicks']
    if pd.isna(zw) or zw<=0: zw=200
    return {'t1':0.5*zw,'t2':1.0*zw,'stp':1.5*zw,'tc':160,'adv_thr':75,'bounce_thr':25,'bounce_win':50}
s, rdf = run_strat("ZR + no-bounce", sim_2leg_nobounce, True, zr_nb_args)
strategies['zr_nb'] = s
out(f"| ZR + 5t + no-bounce 75/25/50 | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# 6. ZR + stop floor max(1.5x, 120t)
s, rdf = run_strat("ZR + stop floor", sim_2leg, True, zr_floor_args)
strategies['zr_floor'] = s
out(f"| ZR + 5t + stop floor max(1.5x,120t) | {s['n']} | {s['wr']:.1f}% | {s['pf']:.2f} | {s['ev']:.1f} | {s['maxdd']:.0f} |")

# Best zone-rel
best_zr_key = max(['zr_base','zr_5t','zr_be','zr_trail','zr_nb','zr_floor'],
                  key=lambda k: strategies[k]['ev'])
bz = strategies[best_zr_key]
out(f"| **Best ZR: {best_zr_key}** | {bz['n']} | {bz['wr']:.1f}% | {bz['pf']:.2f} | {bz['ev']:.1f} | {bz['maxdd']:.0f} |")

# ── OVERALL BEST ──────────────────────────────────────────────────────
out()
out("### OVERALL BEST")
out()
out("| Strategy | Fills | WR | PF | EV/opp | Max DD |")
out("|----------|:---:|:---:|:---:|:---:|:---:|")
out(f"| Best fixed: {best_fixed_key} | {bf['n']} | {bf['wr']:.1f}% | {bf['pf']:.2f} | {bf['ev']:.1f} | {bf['maxdd']:.0f} |")
out(f"| Best ZR: {best_zr_key} | {bz['n']} | {bz['wr']:.1f}% | {bz['pf']:.2f} | {bz['ev']:.1f} | {bz['maxdd']:.0f} |")

overall_key = best_fixed_key if bf['ev'] > bz['ev'] else best_zr_key
ov = bf if bf['ev'] > bz['ev'] else bz
out(f"| **OVERALL: {overall_key}** | {ov['n']} | {ov['wr']:.1f}% | {ov['pf']:.2f} | {ov['ev']:.1f} | {ov['maxdd']:.0f} |")

out()
out("**WARNING: All 'best' parameters selected on P2 data. This is the OVERFITTED CEILING.**")
out("**Real OOS performance will be lower. Nothing enters autotrader spec without P1 confirmation.**")

# ══════════════════════════════════════════════════════════════════════
# SAVE OUTPUTS
# ══════════════════════════════════════════════════════════════════════
print("\nSaving outputs...")

# Add pnl_zone_rel to invest CSV
invest['pnl_zone_rel'] = df.set_index('trade_id').loc[invest['trade_id'].values, 'pnl_zone_rel'].values
assert len(invest) == 312
invest.to_csv(INVEST_CSV, index=False)
print(f"  Updated CSV: {len(invest)} rows, {len(invest.columns)} cols")

# Build combined report
summary = """# Zone Touch Exit Investigation — Combined Report
## P2 Data: 312 trades (187 CT, 125 WT) | seg3_ModeB + variants

---

## SUMMARY

### ACTIONABLE (clear improvement, robust signal)

1. **Zone-relative exits (0.5x/1.0x/1.5x zone_width)** — NEEDS P1 CONFIRMATION
   - P2 result: EV 107.4 vs 43.3 fixed baseline (2.5x improvement)
   - 2-leg (67/33): T1=0.5x zw, T2=1.0x zw, Stop=1.5x zw, TC=160
   - Works across all zone widths; strongest for 150t+ zones
   - Risk: narrow zones (50-100t) have tight stops (75-150t), lower WR

2. **CT 5t limit entry** — NEEDS P1 CONFIRMATION
   - P2 result: 177/187 CT fill (95%), zero CT losses with fixed 40t/190t exits
   - 5t deeper entry captures the penetration bounce more reliably
   - Risk: 10 CT trades (5%) do not fill and are skipped

3. **Stop floor for narrow zones: max(1.5x zw, 120t)** — NEEDS P1 CONFIRMATION
   - Protects narrow zone trades from premature stop-outs
   - Minimal impact on wide zones (1.5x zw already > 120t for zones > 80t)

### DIAGNOSTIC (interesting pattern, needs more data)

1. **Losers penetrate FAST** (9.6 t/bar at 10 bars vs 4.1 for winners)
   - Opposite of initial hypothesis (slow drift)
   - 100t in 10 bars rule: catches 41% of losers at 3% FP, PF +0.06
   - Too selective to be primary exit — supplementary signal at best

2. **Opposite edge cross** — 28% of losers vs 4.6% of winners
   - Exit at edge+25t: 9 losses saved, 6 winners killed (net PF 3.35)
   - Signal fires too late (damage already done) — marginal improvement

3. **No-bounce rules** — TYPE 2 (50t adv, no 20t close bounce in 30 bars)
   - Zero triggers on P2 data — all adverse trades bounce by close
   - Losing pattern is repeated shallow bounces that fail, not continuous drive
   - Need tick-level data or smaller bars to detect bounce quality

4. **WT losers never reach T1** (0% at all bar checkpoints)
   - WT losses are identifiable early — flat MFE by bar 10 is a strong signal
   - Potential for WT-specific early exit if MFE < 20t at bar 15-20

5. **Battleground stall analysis** — LOW CONFIDENCE (n=3 unique events)
   - Winners and losers both bounce within 2-3 bars of max pen
   - No distinguishing stall pattern at current bar granularity

### NOT VIABLE (tested and failed)

1. **Breakeven step-up** — destroys PF at all levels except T1-coincident
   - BE@10-30t: kills 85-95% of remaining position value
   - The strategy needs room to oscillate; BE removes that room
   - Only BE@T1 (40t CT, 0.5x zw) is neutral/slightly positive

2. **Fixed trail with T2 cap** — underperforms fixed T2
   - Trail 20-50t with 80t cap: all slightly worse than fixed T2=80t
   - Only trail with NO CAP shows improvement (lets winners run)

3. **Halfway timecap rule** (adverse >50t at bar 60) — PF drops 1.42
   - Kills 11% of winners for only 56% loser catch rate

### RECOMMENDED NEXT STEPS (priority order)

1. **P1 validation of zone-relative framework** — highest priority
   - Test 0.5x/1.0x/1.5x 2-leg on P1 data
   - If PF > 3.0 on P1, this is the primary exit upgrade

2. **P1 validation of CT 5t limit entry**
   - Verify fill rate and zero-loss claim on P1 data
   - If confirmed, adopt for CT regardless of exit framework

3. **P1 test of stop floor max(1.5x zw, 120t)**
   - Check if 50-100t zone performance improves without harming wider zones

4. **P1 test of zone-relative trail (0.15x zw, no T2 cap)**
   - If zone-rel framework confirmed, this is the next optimization layer

5. **Investigate WT early exit signal (MFE < 20t at bar 15-20)**
   - Need P1 data to confirm WT losers consistently show flat early MFE
   - Could reduce WT losses with minimal winner impact

6. **Test combined: 5t CT + zone-rel exits + stop floor + trail**
   - Only after individual components validated on P1
   - Combined overfitting risk is high — test each layer incrementally

---

"""

# Read part 1 and part 2 markdown if they exist
p1_content = ""
p2_content = ""
try:
    with open(PART2_MD, 'r', encoding='utf-8') as f:
        p2_content = f.read()
except:
    p2_content = "(Part 2 results — see exit_investigation_part2.md)\n"

# Part 1 may not have a separate md file — it was printed to console
p1_content = "(Part 1 results — see console output from exit_investigation_part1.py)\n"

p3_content = md_buf.getvalue()

combined = summary + "\n---\n\n## PART 1: Battleground Profiling + Zone-Width-Relative Exits\n\n" + p1_content
combined += "\n---\n\n## PART 2: Penetration Dynamics + Exit Re-Optimization\n\n" + p2_content
combined += "\n---\n\n## PART 3: Interaction Effects + Head-to-Head\n\n" + p3_content

with open(REPORT_MD, 'w', encoding='utf-8') as f:
    f.write(combined)
print(f"  Report saved to {REPORT_MD}")

print("\n" + "="*70)
print("FINAL VERIFICATION")
print("="*70)
final = pd.read_csv(INVEST_CSV)
print(f"  Rows: {final.shape[0]}")
print(f"  Columns: {final.shape[1]}")
print(f"  pnl_zone_rel present: {'pnl_zone_rel' in final.columns}")
print(f"  pnl_zone_rel nulls: {final['pnl_zone_rel'].isna().sum()}")

print("\nDone — Part 3 of 3 complete.")
