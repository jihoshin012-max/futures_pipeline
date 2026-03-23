# Visual Spot-Check Guide — NQ Zone Touch

Reference card for Sierra Chart verification. Pre-computed prices for all levels.
Open each day's NQ 250-volume chart and walk through the checklist.

---

## Selected Days

| Day | ZR trades | FX trades | FX-only | Coverage |
|-----|-----------|-----------|---------|----------|
| **12/1/2025** | 5 | 5+1 | 1 | CT+WT, Win+Loss, wide zones (231-393t), FX-only trade |
| **12/12/2025** | 2 | 4 | 2 | CT+WT, Win+Loss, wide zones (201-330t), 2 FX-only trades |
| **9/22/2025** | 3 | 3 | 0 | CT+WT, Win+Loss, narrow zones (54-94t), first trades in P1 |

Combined: 10 ZR trades, 12 FX trades, 3 FX-only. Covers CT limit entry, WT market entry, TARGET_1, TARGET_2, STOP, TIMECAP, narrow and wide zones, and trades where FIXED/ZONEREL diverge.

---

## Day 1: December 1, 2025

### Trade 1 — rbi=117888 | DEMAND 90m | LONG WT | score=16.90

**Zone:** Top=25251.00, Bot=25193.25 (width=231t)
**Touch:** 2025-12-01 08:47:45

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry type | MARKET | MARKET |
| Entry | bar 117889 @ **25255.75** | @ **25255.75** |
| T1 | **25284.75** (+116t) | **25270.75** (+60t) |
| T2 | **25313.50** (+231t) | **25275.75** (+80t) |
| Stop | **25169.00** (-347t) | **25195.75** (-240t) |
| Result | T1+T2 **+150.95t** 136 bars | T1+T2 **+63.60t** 22 bars |

Checklist:
- [ ] V4 draws a demand zone at 25251.00/25193.25 (90m TF)
- [ ] Price touches zone edge near 08:47:45
- [ ] Entry at next bar open = 25255.75
- [ ] ZR: price reaches 25284.75 (T1), then 25313.50 (T2) by bar 118024
- [ ] FX: price reaches 25270.75 (T1), then 25275.75 (T2) by bar 117910 — exits 114 bars earlier
- [ ] **Key difference:** FIXED captures 80t, ZONEREL captures 231t on the same entry

---

### Trade 2 — rbi=118447 | DEMAND 30m | LONG CT | score=21.59

**Zone:** Top=25296.75, Bot=25209.25 (width=350t)
**Touch:** 2025-12-01 10:34:03
**CT limit:** 25296.75 - 5×0.25 = **25295.50** (5t inside zone top)

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry type | LIMIT_5T | LIMIT_5T |
| Entry | bar 118448 @ **25295.50** | @ **25295.50** |
| T1 | **25339.25** (+175t) | **25305.50** (+40t) |
| T2 | **25383.00** (+350t) | **25315.50** (+80t) |
| Stop | **25164.25** (-525t) | **25248.00** (-190t) |
| Result | T1+T2 **+229.75t** 115 bars | T1+T2 **+50.20t** 23 bars |

Checklist:
- [ ] V4 draws a demand zone at 25296.75/25209.25 (30m TF)
- [ ] Price touches zone edge near 10:34:03
- [ ] CT limit: verify price trades down to 25295.50 (5t below zone top 25296.75)
- [ ] ZR: price reaches 25339.25 (T1), then 25383.00 (T2)
- [ ] FX: price reaches 25305.50 (T1), then 25315.50 (T2) — exits 92 bars earlier
- [ ] **Key difference:** Wide zone (350t) — ZR captures full zone width, FIXED capped at 80t

---

### Trade 3 — rbi=118662 | DEMAND 30m | LONG CT | score=18.62

**Zone:** Top=25365.75, Bot=25267.50 (width=393t)
**Touch:** 2025-12-01 11:10:23
**CT limit:** 25365.75 - 1.25 = **25364.50**

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry type | LIMIT_5T | LIMIT_5T |
| Entry | bar 118664 @ **25364.50** | @ **25364.50** |
| T1 | **25413.75** (+197t) | **25374.50** (+40t) |
| T2 | **25462.75** (+393t) | **25384.50** (+80t) |
| Stop | **25217.00** (-590t) | **25317.00** (-190t) |
| Result | T1+TIMECAP **+227.00t** 160 bars | T1+T2 **+50.20t** 68 bars |

Checklist:
- [ ] V4 draws a demand zone at 25365.75/25267.50 (30m TF)
- [ ] CT limit fill at 25364.50 (bar 118664)
- [ ] ZR: T1 fills, T2 does NOT fill within 160 bars (TIMECAP)
- [ ] FX: T1+T2 both fill within 68 bars
- [ ] **Key difference:** ZR Stop at 25217.00 (590t!) vs FX Stop at 25317.00 (190t). Wide zone = huge ZR stop.

---

### Trade 4 — rbi=118914 | SUPPLY 15m | SHORT WT | score=17.66 (THE LOSER)

**Zone:** Top=25478.00, Bot=25443.50 (width=138t)
**Touch:** 2025-12-01 12:17:14

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry type | MARKET | MARKET |
| Entry | bar 118915 @ **25444.00** | @ **25444.00** |
| T1 | **25426.75** (+69t) | **25429.00** (+60t) |
| T2 | **25409.50** (+138t) | **25424.00** (+80t) |
| Stop | **25495.75** (-207t) | **25504.00** (-240t) |
| Result | STOP+STOP **-210.00t** 69 bars | T1+TIMECAP **+3.54t** 160 bars |

Checklist:
- [ ] V4 draws a supply zone at 25478.00/25443.50 (15m TF)
- [ ] Entry at next bar open = 25444.00 (short)
- [ ] **ZR STOPS OUT:** Price rises above 25495.75 — verify stop hit on chart
- [ ] **FX SURVIVES:** FX stop is at 25504.00 (further away) — price doesn't reach it
- [ ] FX hits T1 at 25429.00 then TIMECAP on leg2
- [ ] **Key difference:** ZR stop tighter (207t vs 240t) — kills the trade. FX wider stop survives.

---

### Trade 5 — rbi=119044 | SUPPLY 30m | SHORT WT | score=19.38 (ZR-ONLY)

**Zone:** Top=25546.00, Bot=25482.50 (width=254t)
**Touch:** 2025-12-01 13:13:07

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry | bar 119045 @ **25482.00** | *not traded — still in TIMECAP from Trade 4* |
| T1 | **25450.25** (+127t) | — |
| T2 | **25418.50** (+254t) | — |
| Stop | **25577.25** (-381t) | — |
| Result | T1+T2 **+165.91t** 150 bars | — |

Checklist:
- [ ] ZR: verify price reaches 25450.25 (T1) and 25418.50 (T2)
- [ ] FX: verify FIXED is still holding Trade 4 position at this time (TIMECAP exits at bar 119074, this signal fires at bar 119044 — 30 bars before FX exits)

---

### Trade 6 — rbi=119110 | SUPPLY 30m | SHORT WT | score=19.38 (FX-ONLY)

**Zone:** Top=25546.00, Bot=25482.50 (width=254t) — SAME ZONE as Trade 5
**Touch:** 2025-12-01 13:51:47

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry | *not traded — still in position from Trade 5* | bar 119111 @ **25480.75** |
| T1 | — | **25465.75** (+60t) |
| T2 | — | **25460.75** (+80t) |
| Stop | — | **25540.75** (-240t) |
| Result | — | T1+T2 **+63.60t** 27 bars |

Checklist:
- [ ] FX-only: verify ZR is still holding Trade 5 at this time
- [ ] FX: enters at 25480.75 and hits both targets
- [ ] **This is the throughput difference:** FIXED resolves faster → catches extra trades

---

## Day 2: December 12, 2025

### Trade 7 — rbi=137875 | SUPPLY 15m | SHORT WT | score=17.66 (DIVERGENT OUTCOMES)

**Zone:** Top=25402.00, Bot=25319.50 (width=330t)
**Touch:** 2025-12-12 13:12:00

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry type | MARKET | MARKET |
| Entry | bar 137876 @ **25296.75** | @ **25296.75** |
| T1 | **25255.50** (+165t) | **25281.75** (+60t) |
| T2 | **25214.25** (+330t) | **25276.75** (+80t) |
| Stop | **25420.50** (-495t) | **25356.75** (-240t) |
| Result | TIMECAP+TIMECAP **-40.00t** 160b | STOP+STOP **-243.00t** 16b |

Checklist:
- [ ] V4 draws a supply zone at 25402.00/25319.50 (15m TF)
- [ ] Entry at 25296.75 (short) — note entry is BELOW zone bot (25319.50)
- [ ] **FX STOPS OUT at bar 137891 (16 bars in):** Price rises above 25356.75
- [ ] **ZR SURVIVES 160 bars:** ZR stop at 25420.50 is much further — verify price stays below it
- [ ] ZR eventually time-caps with small loss (-40t) vs FX full stop (-243t)
- [ ] **Key difference:** Wide zone (330t) = ZR stop 495t away, FX only 240t. Opposite of Trade 4.

---

### Trade 8 — rbi=137960 | SUPPLY 15m | SHORT CT | score=17.66 (FX-ONLY #1)

**Zone:** Top=25402.00, Bot=25319.50 (width=330t) — SAME ZONE as Trade 7
**Touch:** 2025-12-12 13:23:24

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry | *in position from Trade 7 (TIMECAP)* | bar 137961 @ **25320.75** |
| T1 | — | **25310.75** (+40t) |
| T2 | — | **25300.75** (+80t) |
| Stop | — | **25368.25** (-190t) |
| Result | — | T1+T2 **+50.20t** 59 bars |

Checklist:
- [ ] FX-only: ZR still holding Trade 7 (TIMECAP at bar 138035, this signal at bar 137960)
- [ ] FX stopped out on Trade 7 at bar 137891 — flat by now, free to enter
- [ ] FX enters at 25320.75 and hits both targets — recovers from Trade 7 loss

---

### Trade 9 — rbi=138377 | DEMAND 15m | LONG CT | score=16.90

**Zone:** Top=25185.75, Bot=25135.50 (width=201t)
**Touch:** 2025-12-12 15:35:16
**CT limit:** 25185.75 - 1.25 = **25184.50**

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry type | LIMIT_5T | LIMIT_5T |
| Entry | bar 138378 @ **25184.50** | @ **25184.50** |
| T1 | **25209.75** (+101t) | **25194.50** (+40t) |
| T2 | **25234.75** (+201t) | **25204.50** (+80t) |
| Stop | **25109.00** (-302t) | **25137.00** (-190t) |
| Result | T1+TIMECAP **+103.94t** 160b | T1+T2 **+50.20t** 45b |

Checklist:
- [ ] CT limit fill at 25184.50
- [ ] ZR: T1 fills at 25209.75, T2 does NOT fill (TIMECAP at 160 bars)
- [ ] FX: T1+T2 both fill within 45 bars

---

### Trade 10 — rbi=138448 | DEMAND 15m | LONG WT | score=16.90 (FX-ONLY #2)

**Zone:** Top=25185.75, Bot=25135.50 (width=201t) — SAME ZONE as Trade 9
**Touch:** 2025-12-12 15:50:50

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry | *in position from Trade 9 (TIMECAP)* | bar 138449 @ **25190.00** |
| T1 | — | **25205.00** (+60t) |
| T2 | — | **25210.00** (+80t) |
| Stop | — | **25130.00** (-240t) |
| Result | — | T1+T2 **+63.60t** 37 bars |

Checklist:
- [ ] FX-only: ZR still holding Trade 9
- [ ] FX enters at 25190.00 and hits both targets

---

## Day 3: September 22, 2025 (First P1 Trades)

### Trade 11 — rbi=1669 | DEMAND 15m | LONG CT | score=16.90

**Zone:** Top=24996.25, Bot=24982.75 (width=54t)
**Touch:** 2025-09-22 15:45:54
**CT limit:** 24996.25 - 1.25 = **24995.00**

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry type | LIMIT_5T | LIMIT_5T |
| Entry | bar 1670 @ **24995.00** | @ **24995.00** |
| T1 | **25001.75** (+27t) | **25005.00** (+40t) |
| T2 | **25008.50** (+54t) | **25015.00** (+80t) |
| Stop | **24965.00** (-120t) | **24947.50** (-190t) |
| Result | T1+T2 **+32.91t** 16b | T1+T2 **+50.20t** 16b |

Checklist:
- [ ] First trade in P1 — V4 draws a 15m demand zone at 24996.25/24982.75
- [ ] CT limit: price trades at or below 24995.00 (5t inside 24996.25 top)
- [ ] Both variants fill T1+T2 on same bar (16 bars held)
- [ ] **Key difference:** FIXED captures more (80t vs 54t) because zone is narrow (54t). ZR targets cap at zone width.

---

### Trade 12 — rbi=1703 | DEMAND 15m | LONG WT | score=16.90

**Zone:** Top=24996.25, Bot=24982.75 (width=54t) — SAME ZONE as Trade 11
**Touch:** 2025-09-22 15:52:20

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry type | MARKET | MARKET |
| Entry | bar 1704 @ **24997.75** | @ **24997.75** |
| T1 | **25004.50** (+27t) | **25012.75** (+60t) |
| T2 | **25011.25** (+54t) | **25017.75** (+80t) |
| Stop | **24967.75** (-120t) | **24937.75** (-240t) |
| Result | T1+T2 **+32.91t** 36b | T1+TIMECAP **+29.61t** 160b |

Checklist:
- [ ] Same zone, second touch — WT (market entry at next bar open)
- [ ] ZR: both targets fill within 36 bars
- [ ] FX: T1 fills but T2 at 25017.75 (+80t) does NOT fill — TIMECAP at 160 bars
- [ ] **Key difference:** Narrow zone — ZR T2=54t fills easily. FX T2=80t is 26t beyond zone width and never reaches it.

---

### Trade 13 — rbi=1893 | SUPPLY 15m | SHORT WT | score=16.90

**Zone:** Top=25016.50, Bot=24993.00 (width=94t)
**Touch:** 2025-09-22 19:25:36

| | ZONEREL | FIXED |
|---|---------|-------|
| Entry type | MARKET | MARKET |
| Entry | bar 1894 @ **24989.75** | @ **24989.75** |
| T1 | **24978.00** (+47t) | **24974.75** (+60t) |
| T2 | **24966.25** (+94t) | **24969.75** (+80t) |
| Stop | **25025.00** (-141t) | **25049.75** (-240t) |
| Result | T1+STOP **-18.04t** 116b | TIMECAP+TIMECAP **+1.00t** 160b |

Checklist:
- [ ] Supply zone at 25016.50/24993.00 — short entry
- [ ] **ZR: T1 fills, then STOP at 25025.00 (141t)** — verify price rises above 25025.00
- [ ] **FX: Stop at 25049.75 (240t) — never hit.** TIMECAP at 160 bars with small profit
- [ ] **Key difference:** ZR stop closer (141t vs 240t) — gets stopped out on a retracement that FX survives

---

## Summary: What to Look For

### Entry Type Verification
| Trade | Type | Verify |
|-------|------|--------|
| 1, 4, 5, 6, 7, 8, 10, 12, 13 | MARKET | Entry = next bar Open after touch |
| 2, 3, 9, 11 | LIMIT_5T | Entry = 5 ticks inside zone edge (zone_top - 1.25 for demand, zone_bot + 1.25 for supply) |

### FX-Only Trades (Throughput Difference)
| Trade | Day | Why FX trades but ZR doesn't |
|-------|-----|------------------------------|
| 6 (rbi=119110) | 12/1 | ZR holding Trade 5 (T1+T2, 150 bars). FX exited Trade 4 at TIMECAP, then entered Trade 5 earlier, already exited. |
| 8 (rbi=137960) | 12/12 | ZR holding Trade 7 (TIMECAP, 160 bars). FX stopped out of Trade 7 at bar 16, free to re-enter same zone. |
| 10 (rbi=138448) | 12/12 | ZR holding Trade 9 (TIMECAP, 160 bars). FX exited Trade 9 at T1+T2 in 45 bars. |

### PASS Criteria
Each trade: zone exists, entry price matches, exit type matches, exit bar is plausible.
If all 13 trades check out visually: **PASS — proceed to ZRA+ZB4 consolidation.**
