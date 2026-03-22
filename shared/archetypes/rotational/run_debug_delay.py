# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: Debug re-entry delay verification
# LAST RUN: unknown

"""Debug re-entry delay: verify implementation, re-run with corrected logic."""

import sys
import json
import datetime as dt_mod
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from shared.data_loader import load_bars

EXCLUDE_HOURS = {1, 19, 20}
_P1_MID = dt_mod.date(2025, 9, 21) + (dt_mod.date(2025, 12, 14) - dt_mod.date(2025, 9, 21)) / 2


def run_delay(prices, dts, n, sr=15.0, sa=40.0, delay_val=0, ct=3):
    ts = 0.25
    state = -1
    wp = 0.0
    anc = 0.0
    pos = 0
    avg_e = 0.0
    cid = 0
    cs = 0
    delay_rem = 0
    cycles = []
    ctr = []

    for i in range(n):
        p = prices[i]
        if delay_rem > 0:
            delay_rem -= 1
            continue

        if state == -1:
            if wp == 0.0:
                wp = p
                continue
            if p - wp >= sr:
                cid += 1; state = 1; anc = p; pos = 1; avg_e = p; cs = i
                ctr = [{"a": "SEED", "p": p}]
            elif wp - p >= sr:
                cid += 1; state = 2; anc = p; pos = 1; avg_e = p; cs = i
                ctr = [{"a": "SEED", "p": p}]
            continue

        dist = p - anc
        fav = (dist >= sr) if state == 1 else ((-dist) >= sr)
        adv = ((-dist) >= sa) if state == 1 else (dist >= sa)

        if fav:
            d = "L" if state == 1 else "S"
            ets = [t for t in ctr if t["a"] in ("SEED", "R", "ADD")]
            tq = len(ets)
            wa = sum(t["p"] for t in ets) / tq if tq else p
            gr = ((p - wa) / ts * tq) if d == "L" else ((wa - p) / ts * tq)
            cost = ct + len([t for t in ets if t["a"] == "ADD"]) * ct + ct * pos
            nt = gr - cost
            cycles.append({"cid": cid, "gr": gr, "nt": nt, "cs": cs})

            # Delay: after losing cycle, go flat + wait (NO reversal entry)
            if delay_val > 0 and nt < 0:
                delay_rem = delay_val
                state = -1
                wp = 0.0
                pos = 0
                continue

            # Normal: reversal into new cycle
            cid += 1
            state = 2 if d == "L" else 1
            anc = p; pos = 1; avg_e = p; cs = i
            ctr = [{"a": "R", "p": p}]

        elif adv:
            anc = p
            oq = pos; pos += 1
            avg_e = (avg_e * oq + p) / pos
            ctr.append({"a": "ADD", "p": p})

    # Finalize
    if state in (1, 2) and ctr:
        lp = prices[n - 1]
        d = "L" if state == 1 else "S"
        ets = [t for t in ctr if t["a"] in ("SEED", "R", "ADD")]
        tq = len(ets)
        wa = sum(t["p"] for t in ets) / tq if tq else lp
        gr = ((lp - wa) / ts * tq) if d == "L" else ((wa - lp) / ts * tq)
        cost = ct + len([t for t in ets if t["a"] == "ADD"]) * ct + ct * pos
        nt = gr - cost
        cycles.append({"cid": cid, "gr": gr, "nt": nt, "cs": cs})

    return cycles


def main():
    with open(Path(__file__).parent / "rotational_params.json") as f:
        cfg = json.load(f)

    print("Loading tick data...")
    tick_bars = load_bars(cfg["bar_data_primary"]["bar_data_1tick_rot"])
    tick_p1a = tick_bars[tick_bars["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    prices = tick_p1a["Last"].values.astype(np.float64)
    dts = tick_p1a["datetime"].values
    n = len(prices)
    print(f"Tick P1a: {n:,}")

    print(f"\n{'Delay':>6} {'Cyc':>6} {'GrPF':>7} {'NPF@3':>7} {'NPF@2':>7} "
          f"{'Net@3t':>9} {'Net@2t':>9} {'Ret':>6}")
    print("-" * 65)

    for dv in [0, 25, 50, 100, 200, 400]:
        cyc = run_delay(prices, dts, n, sr=15.0, sa=40.0, delay_val=dv)
        cdf = pd.DataFrame(cyc)
        cdf["hour"] = pd.to_datetime([dts[c["cs"]] for c in cyc]).hour
        cf = cdf[~cdf["hour"].isin(EXCLUDE_HOURS)]

        nn = len(cf)
        if nn == 0:
            print(f"{dv:>6} {'N/A':>6}")
            continue

        gw = cf[cf["gr"] > 0]["gr"].sum()
        gl = abs(cf[cf["gr"] <= 0]["gr"].sum())
        gpf = gw / gl if gl > 0 else 0

        # Net at 3t (already computed in nt column)
        nw3 = cf[cf["nt"] > 0]["nt"].sum()
        nl3 = abs(cf[cf["nt"] <= 0]["nt"].sum())
        npf3 = nw3 / nl3 if nl3 > 0 else 0

        # Net at 2t: recompute with 2/3 cost
        cf = cf.copy()
        cf["nt2"] = cf["gr"] - (cf["gr"] - cf["nt"]) * 2 / 3
        nw2 = cf[cf["nt2"] > 0]["nt2"].sum()
        nl2 = abs(cf[cf["nt2"] <= 0]["nt2"].sum())
        npf2 = nw2 / nl2 if nl2 > 0 else 0

        net3 = cf["nt"].sum()
        net2 = cf["nt2"].sum()
        ret = nn / 2107 * 100  # baseline

        m = "<<<" if npf3 > 1.2 else ("<<" if npf3 > 1.0 else ("< " if npf2 > 1.0 else ""))
        print(f"{dv:>6} {nn:>6} {gpf:>7.4f} {npf3:>7.4f} {npf2:>7.4f} "
              f"{net3:>+9,.0f} {net2:>+9,.0f} {ret:>5.1f}% {m}")

    print("\nDone.")


if __name__ == "__main__":
    main()
