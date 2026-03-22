# Prompt 1a — Feature Screening Report (v3.1)
Generated: 2026-03-21T23:27:30.261917
P1 only: 4701 touches. P2 NOT USED.
Baseline anchor: PF @3t = 0.8984, R/P @60 = 1.007

## Feature Screening Rankings (by R/P spread @60)

| Rank | Feature | Best R/P @60 | Worst R/P @60 | Spread @60 | Horizons | MWU p | Cohen d | Class |
|------|---------|-------------|--------------|-----------|----------|-------|---------|-------|
| 1 | F10_PriorPenetration | 1.602 | 0.624 | 0.977 | 4/4 | 0.0000 | 0.265 | STRONG |
| 2 | F04_CascadeState | 1.473 | 0.894 | 0.580 | 4/4 | 0.0057 | 0.102 | STRONG |
| 3 | F05_Session | 1.234 | 0.765 | 0.470 | 2/4 | 0.9992 | -0.020 | STRONG |
| 4 | F01_Timeframe | 1.022 | 0.686 | 0.336 | 3/4 | 0.0019 | 0.261 | STRONG |
| 5 | F21_ZoneAge (EXP) | 1.097 | 0.834 | 0.263 | 3/4 | 0.0000 | 0.160 | MODERATE |
| 6 | F12_BarDuration | 1.065 | 0.817 | 0.248 | 3/4 | 0.9998 | -0.143 | MODERATE |
| 7 | F24_NearestZoneDist (EXP) | 1.082 | 0.842 | 0.240 | 3/4 | 0.0000 | 0.158 | MODERATE |
| 8 | F20_VPDistance | 1.060 | 0.835 | 0.225 | 3/4 | 0.1066 | 0.090 | MODERATE |
| 9 | F13_ClosePosition | 1.060 | 0.848 | 0.213 | 2/4 | 0.0000 | 0.110 | MODERATE |
| 10 | F16_ZZOscillator | 1.054 | 0.849 | 0.204 | 3/4 | 0.0008 | 0.110 | MODERATE |
| 11 | F25_BreakHistory (EXP) | 1.055 | 0.874 | 0.181 | 2/4 | 0.0049 | 0.144 | MODERATE |
| 12 | F11_DeltaDivergence | 1.020 | 0.843 | 0.177 | 1/4 | 0.0000 | 0.119 | MODERATE |
| 13 | F23_CrossTFConfluence (EXP) | 1.035 | 0.874 | 0.160 | 2/4 | 0.0000 | 0.122 | MODERATE |
| 14 | F06_ApproachVelocity | 1.019 | 0.903 | 0.115 | 1/4 | 0.9999 | -0.161 | WEAK |
| 15 | F02_ZoneWidth | 1.005 | 0.893 | 0.112 | 0/4 | 0.6887 | -0.010 | WEAK |
| 16 | F09_ZW_ATR | 0.978 | 0.886 | 0.092 | 0/4 | 0.0000 | 0.158 | MODERATE |
| 17 | F22_RecentBreakRate (EXP) | 0.979 | 0.909 | 0.070 | 0/4 | 1.0000 | -0.192 | WEAK |
| 18 | F15_ZZSwingRegime | 0.980 | 0.912 | 0.069 | 0/4 | 0.6996 | -0.024 | WEAK |
| 19 | F14_AvgOrderSize | 0.987 | 0.920 | 0.067 | 0/4 | 0.1973 | 0.008 | WEAK |
| 20 | F17_ATRRegime | 0.965 | 0.912 | 0.054 | 0/4 | 0.0004 | 0.159 | MODERATE |
| 21 | F07_Deceleration | 0.971 | 0.920 | 0.051 | 0/4 | 0.6220 | 0.012 | WEAK |
| 22 | F19_VPConsumption | 0.949 | 0.930 | 0.019 | 0/4 | 0.0000 | 0.188 | MODERATE |
| 23 | F08_PriorRxnSpeed | 0.865 | 0.853 | 0.012 | 0/4 | 0.0000 | 0.320 | MODERATE |

**STRONG:** ['F10_PriorPenetration', 'F04_CascadeState', 'F05_Session', 'F01_Timeframe']
**SBB-MASKED:** ['F21_ZoneAge', 'F09_ZW_ATR', 'F02_ZoneWidth']
**MODERATE:** ['F21_ZoneAge', 'F12_BarDuration', 'F24_NearestZoneDist', 'F20_VPDistance', 'F13_ClosePosition', 'F16_ZZOscillator', 'F25_BreakHistory', 'F11_DeltaDivergence', 'F23_CrossTFConfluence', 'F09_ZW_ATR', 'F17_ATRRegime', 'F19_VPConsumption', 'F08_PriorRxnSpeed']
**WEAK:** ['F06_ApproachVelocity', 'F02_ZoneWidth', 'F22_RecentBreakRate', 'F15_ZZSwingRegime', 'F14_AvgOrderSize', 'F07_Deceleration']

## Multi-Horizon Detail (all features)

### F10_PriorPenetration [STRONG]
- @30: spread=0.625, p=0.0000, d=0.314, best=Low, worst=Mid
  - Low: R/P=1.314, Rxn=99.6, Pen=75.8, n=1006
  - Mid: R/P=0.689, Rxn=74.5, Pen=108.1, n=1029
  - High: R/P=0.699, Rxn=93.3, Pen=133.5, n=1004
- @60: spread=0.977, p=0.0000, d=0.265, best=Low, worst=High
  - Low: R/P=1.602, Rxn=153.7, Pen=96.0, n=1006
  - Mid: R/P=0.693, Rxn=104.3, Pen=150.5, n=1029
  - High: R/P=0.624, Rxn=122.9, Pen=196.7, n=1004
- @120: spread=1.312, p=0.0000, d=0.410, best=Low, worst=High
  - Low: R/P=1.871, Rxn=232.2, Pen=124.1, n=1006
  - Mid: R/P=0.702, Rxn=146.3, Pen=208.6, n=1029
  - High: R/P=0.559, Rxn=165.0, Pen=295.3, n=1004
- @full: spread=2.860, p=0.0000, d=0.443, best=Low, worst=High
  - Low: R/P=3.289, Rxn=792.2, Pen=240.9, n=1006
  - Mid: R/P=1.585, Rxn=645.6, Pen=407.4, n=1029
  - High: R/P=0.429, Rxn=488.5, Pen=1138.5, n=1004

### F04_CascadeState [STRONG]
- @30: spread=0.549, p=0.0364, d=0.087, best=NO_PRIOR, worst=PRIOR_BROKE
  - PRIOR_BROKE: R/P=0.873, Rxn=96.1, Pen=110.2, n=3995
  - PRIOR_HELD: R/P=1.265, Rxn=94.5, Pen=74.7, n=538
  - NO_PRIOR: R/P=1.422, Rxn=105.6, Pen=74.3, n=168
- @60: spread=0.580, p=0.0057, d=0.102, best=NO_PRIOR, worst=PRIOR_BROKE
  - PRIOR_BROKE: R/P=0.894, Rxn=137.9, Pen=154.3, n=3995
  - PRIOR_HELD: R/P=1.342, Rxn=136.8, Pen=102.0, n=538
  - NO_PRIOR: R/P=1.473, Rxn=152.1, Pen=103.2, n=168
- @120: spread=0.498, p=0.0167, d=0.078, best=NO_PRIOR, worst=PRIOR_BROKE
  - PRIOR_BROKE: R/P=0.908, Rxn=196.0, Pen=215.9, n=3995
  - PRIOR_HELD: R/P=1.323, Rxn=193.6, Pen=146.3, n=538
  - NO_PRIOR: R/P=1.406, Rxn=210.3, Pen=149.5, n=168
- @full: spread=0.484, p=0.9923, d=-0.314, best=NO_PRIOR, worst=PRIOR_BROKE
  - PRIOR_BROKE: R/P=1.054, Rxn=666.0, Pen=632.1, n=3995
  - PRIOR_HELD: R/P=1.340, Rxn=492.0, Pen=367.3, n=538
  - NO_PRIOR: R/P=1.537, Rxn=484.8, Pen=315.4, n=168

### F05_Session [STRONG]
- @30: spread=0.341, p=0.0324, d=0.047, best=PreRTH, worst=Overnight
  - Overnight: R/P=0.795, Rxn=109.3, Pen=137.5, n=1335
  - PreRTH: R/P=1.136, Rxn=113.7, Pen=100.1, n=621
  - OpeningDrive: R/P=0.908, Rxn=86.4, Pen=95.1, n=936
  - Midday: R/P=0.874, Rxn=78.5, Pen=89.8, n=999
  - Close: R/P=1.125, Rxn=94.9, Pen=84.3, n=810
- @60: spread=0.470, p=0.9992, d=-0.020, best=Close, worst=Overnight
  - Overnight: R/P=0.765, Rxn=150.8, Pen=197.2, n=1335
  - PreRTH: R/P=1.153, Rxn=159.6, Pen=138.4, n=621
  - OpeningDrive: R/P=0.951, Rxn=124.1, Pen=130.5, n=936
  - Midday: R/P=0.947, Rxn=114.3, Pen=120.7, n=999
  - Close: R/P=1.234, Rxn=147.2, Pen=119.2, n=810
- @120: spread=0.483, p=0.9788, d=-0.010, best=Close, worst=Overnight
  - Overnight: R/P=0.755, Rxn=213.1, Pen=282.1, n=1335
  - PreRTH: R/P=1.165, Rxn=220.1, Pen=188.9, n=621
  - OpeningDrive: R/P=0.976, Rxn=176.6, Pen=180.9, n=936
  - Midday: R/P=1.001, Rxn=165.6, Pen=165.4, n=999
  - Close: R/P=1.238, Rxn=210.8, Pen=170.3, n=810
- @full: spread=0.381, p=0.0000, d=0.236, best=OpeningDrive, worst=Overnight
  - Overnight: R/P=0.900, Rxn=597.5, Pen=663.7, n=1335
  - PreRTH: R/P=1.094, Rxn=833.5, Pen=761.6, n=621
  - OpeningDrive: R/P=1.281, Rxn=772.6, Pen=603.2, n=936
  - Midday: R/P=1.183, Rxn=605.6, Pen=512.0, n=999
  - Close: R/P=1.067, Rxn=448.9, Pen=420.9, n=810

### F01_Timeframe [STRONG]
- @30: spread=0.326, p=0.0017, d=0.281, best=30m, worst=480m
  - 15m: R/P=0.910, Rxn=96.6, Pen=106.2, n=1340
  - 30m: R/P=0.979, Rxn=100.6, Pen=102.7, n=972
  - 120m: R/P=0.891, Rxn=96.7, Pen=108.5, n=461
  - 90m: R/P=0.974, Rxn=97.1, Pen=99.7, n=491
  - 60m: R/P=0.947, Rxn=96.0, Pen=101.4, n=606
  - 480m: R/P=0.652, Rxn=74.7, Pen=114.5, n=186
  - 240m: R/P=0.897, Rxn=94.0, Pen=104.8, n=259
  - 360m: R/P=0.859, Rxn=92.8, Pen=108.0, n=222
  - 720m: R/P=0.911, Rxn=98.2, Pen=107.8, n=164
- @60: spread=0.336, p=0.0019, d=0.261, best=30m, worst=480m
  - 15m: R/P=0.908, Rxn=137.0, Pen=150.9, n=1340
  - 30m: R/P=1.022, Rxn=144.7, Pen=141.6, n=972
  - 120m: R/P=0.916, Rxn=138.4, Pen=151.2, n=461
  - 90m: R/P=0.988, Rxn=133.2, Pen=134.8, n=491
  - 60m: R/P=0.977, Rxn=136.1, Pen=139.3, n=606
  - 480m: R/P=0.686, Rxn=112.4, Pen=163.7, n=186
  - 240m: R/P=0.993, Rxn=143.9, Pen=144.9, n=259
  - 360m: R/P=0.876, Rxn=139.2, Pen=158.9, n=222
  - 720m: R/P=0.996, Rxn=152.4, Pen=153.1, n=164
- @120: spread=0.393, p=0.0004, d=0.313, best=30m, worst=480m
  - 15m: R/P=0.904, Rxn=193.2, Pen=213.6, n=1340
  - 30m: R/P=1.079, Rxn=209.8, Pen=194.5, n=972
  - 120m: R/P=0.906, Rxn=195.3, Pen=215.5, n=461
  - 90m: R/P=0.985, Rxn=184.4, Pen=187.2, n=491
  - 60m: R/P=0.995, Rxn=194.5, Pen=195.4, n=606
  - 480m: R/P=0.685, Rxn=156.8, Pen=228.7, n=186
  - 240m: R/P=0.992, Rxn=204.9, Pen=206.6, n=259
  - 360m: R/P=0.883, Rxn=201.5, Pen=228.3, n=222
  - 720m: R/P=0.996, Rxn=210.5, Pen=211.3, n=164
- @full: spread=0.542, p=0.0055, d=0.280, best=720m, worst=15m
  - 15m: R/P=0.937, Rxn=589.9, Pen=629.5, n=1340
  - 30m: R/P=1.105, Rxn=660.7, Pen=598.0, n=972
  - 120m: R/P=1.185, Rxn=674.9, Pen=569.7, n=461
  - 90m: R/P=1.150, Rxn=625.4, Pen=543.8, n=491
  - 60m: R/P=1.023, Rxn=614.2, Pen=600.2, n=606
  - 480m: R/P=0.959, Rxn=532.3, Pen=554.8, n=186
  - 240m: R/P=1.383, Rxn=714.0, Pen=516.3, n=259
  - 360m: R/P=1.279, Rxn=768.6, Pen=601.0, n=222
  - 720m: R/P=1.479, Rxn=788.6, Pen=533.3, n=164

### F21_ZoneAge [MODERATE]
- @30: spread=0.287, p=0.0000, d=0.187, best=Low, worst=High
  - Low: R/P=1.089, Rxn=109.7, Pen=100.8, n=1554
  - Mid: R/P=0.880, Rxn=89.6, Pen=101.8, n=1595
  - High: R/P=0.801, Rxn=89.7, Pen=111.9, n=1552
- @60: spread=0.263, p=0.0000, d=0.160, best=Low, worst=High
  - Low: R/P=1.097, Rxn=155.9, Pen=142.1, n=1554
  - Mid: R/P=0.913, Rxn=127.7, Pen=139.8, n=1595
  - High: R/P=0.834, Rxn=131.5, Pen=157.7, n=1552
- @120: spread=0.267, p=0.0000, d=0.173, best=Low, worst=High
  - Low: R/P=1.127, Rxn=222.8, Pen=197.8, n=1554
  - Mid: R/P=0.890, Rxn=177.8, Pen=199.7, n=1595
  - High: R/P=0.860, Rxn=188.7, Pen=219.4, n=1552
- @full: spread=0.124, p=0.3800, d=0.037, best=High, worst=Mid
  - Low: R/P=1.058, Rxn=629.7, Pen=595.2, n=1554
  - Mid: R/P=1.037, Rxn=631.8, Pen=609.1, n=1595
  - High: R/P=1.161, Rxn=657.7, Pen=566.6, n=1552

### F12_BarDuration [MODERATE]
- @30: spread=0.189, p=1.0000, d=-0.176, best=Mid, worst=High
  - Low: R/P=0.939, Rxn=93.3, Pen=99.4, n=1551
  - Mid: R/P=1.020, Rxn=90.1, Pen=88.3, n=1598
  - High: R/P=0.831, Rxn=105.7, Pen=127.3, n=1551
- @60: spread=0.248, p=0.9998, d=-0.143, best=Mid, worst=High
  - Low: R/P=1.001, Rxn=137.3, Pen=137.1, n=1551
  - Mid: R/P=1.065, Rxn=129.6, Pen=121.7, n=1598
  - High: R/P=0.817, Rxn=148.2, Pen=181.4, n=1551
- @120: spread=0.274, p=0.9993, d=-0.118, best=Mid, worst=High
  - Low: R/P=1.023, Rxn=193.9, Pen=189.5, n=1551
  - Mid: R/P=1.087, Rxn=187.0, Pen=172.1, n=1598
  - High: R/P=0.813, Rxn=208.2, Pen=256.1, n=1551
- @full: spread=0.266, p=0.4085, d=0.031, best=Mid, worst=High
  - Low: R/P=1.149, Rxn=705.0, Pen=613.5, n=1551
  - Mid: R/P=1.195, Rxn=617.6, Pen=517.0, n=1598
  - High: R/P=0.928, Rxn=597.4, Pen=643.4, n=1551

### F24_NearestZoneDist [MODERATE]
- @30: spread=0.146, p=0.0010, d=0.096, best=Low, worst=Mid
  - Low: R/P=1.009, Rxn=101.4, Pen=100.5, n=1557
  - Mid: R/P=0.863, Rxn=93.0, Pen=107.8, n=1587
  - High: R/P=0.891, Rxn=94.5, Pen=106.1, n=1557
- @60: spread=0.240, p=0.0000, d=0.158, best=Low, worst=High
  - Low: R/P=1.082, Rxn=149.6, Pen=138.3, n=1557
  - Mid: R/P=0.920, Rxn=137.2, Pen=149.0, n=1587
  - High: R/P=0.842, Rxn=128.0, Pen=152.1, n=1557
- @120: spread=0.308, p=0.0000, d=0.210, best=Low, worst=High
  - Low: R/P=1.130, Rxn=217.2, Pen=192.3, n=1557
  - Mid: R/P=0.932, Rxn=193.1, Pen=207.1, n=1587
  - High: R/P=0.822, Rxn=178.6, Pen=217.2, n=1557
- @full: spread=0.637, p=0.0000, d=0.255, best=Low, worst=High
  - Low: R/P=1.495, Rxn=746.9, Pen=499.5, n=1557
  - Mid: R/P=0.991, Rxn=604.1, Pen=609.3, n=1587
  - High: R/P=0.858, Rxn=568.6, Pen=662.3, n=1557

### F20_VPDistance [MODERATE]
- @30: spread=0.168, p=0.2246, d=0.054, best=High, worst=Mid
  - Low: R/P=0.888, Rxn=91.9, Pen=103.5, n=467
  - Mid: R/P=0.847, Rxn=80.3, Pen=94.9, n=473
  - High: R/P=1.015, Rxn=84.7, Pen=83.5, n=464
- @60: spread=0.225, p=0.1066, d=0.090, best=High, worst=Mid
  - Low: R/P=0.918, Rxn=131.7, Pen=143.5, n=467
  - Mid: R/P=0.835, Rxn=110.4, Pen=132.3, n=473
  - High: R/P=1.060, Rxn=120.1, Pen=113.3, n=464
- @120: spread=0.271, p=0.0497, d=0.121, best=High, worst=Mid
  - Low: R/P=0.959, Rxn=193.6, Pen=202.0, n=467
  - Mid: R/P=0.829, Rxn=155.8, Pen=187.8, n=473
  - High: R/P=1.100, Rxn=173.8, Pen=158.0, n=464
- @full: spread=0.954, p=0.0025, d=0.080, best=High, worst=Low
  - Low: R/P=0.862, Rxn=599.6, Pen=695.5, n=467
  - Mid: R/P=1.481, Rxn=650.2, Pen=439.1, n=473
  - High: R/P=1.816, Rxn=659.8, Pen=363.3, n=464

### F13_ClosePosition [MODERATE]
- @30: spread=0.233, p=0.0000, d=0.126, best=Low, worst=High
  - Low: R/P=1.027, Rxn=103.0, Pen=100.3, n=1552
  - Mid: R/P=0.949, Rxn=96.1, Pen=101.2, n=1596
  - High: R/P=0.794, Rxn=89.8, Pen=113.1, n=1553
- @60: spread=0.213, p=0.0000, d=0.110, best=Low, worst=High
  - Low: R/P=1.060, Rxn=148.2, Pen=139.8, n=1552
  - Mid: R/P=0.935, Rxn=135.0, Pen=144.4, n=1596
  - High: R/P=0.848, Rxn=131.7, Pen=155.3, n=1553
- @120: spread=0.185, p=0.0000, d=0.127, best=Low, worst=High
  - Low: R/P=1.052, Rxn=209.7, Pen=199.4, n=1552
  - Mid: R/P=0.953, Rxn=194.0, Pen=203.6, n=1596
  - High: R/P=0.867, Rxn=185.2, Pen=213.8, n=1553
- @full: spread=0.036, p=0.2469, d=0.030, best=Mid, worst=High
  - Low: R/P=1.091, Rxn=636.5, Pen=583.5, n=1552
  - Mid: R/P=1.097, Rxn=651.2, Pen=593.4, n=1596
  - High: R/P=1.061, Rxn=630.9, Pen=594.6, n=1553

### F16_ZZOscillator [MODERATE]
- @30: spread=0.213, p=0.0000, d=0.115, best=Mid, worst=Low
  - Low: R/P=0.831, Rxn=94.0, Pen=113.1, n=1563
  - Mid: R/P=1.045, Rxn=106.1, Pen=101.5, n=1578
  - High: R/P=0.888, Rxn=88.7, Pen=99.9, n=1560
- @60: spread=0.204, p=0.0008, d=0.110, best=Mid, worst=Low
  - Low: R/P=0.849, Rxn=135.5, Pen=159.5, n=1563
  - Mid: R/P=1.054, Rxn=151.7, Pen=144.0, n=1578
  - High: R/P=0.938, Rxn=127.4, Pen=135.9, n=1560
- @120: spread=0.164, p=0.0194, d=0.082, best=Mid, worst=Low
  - Low: R/P=0.862, Rxn=193.8, Pen=224.9, n=1563
  - Mid: R/P=1.026, Rxn=209.3, Pen=204.0, n=1578
  - High: R/P=0.988, Rxn=185.5, Pen=187.8, n=1560
- @full: spread=0.201, p=0.4038, d=0.078, best=Mid, worst=Low
  - Low: R/P=0.966, Rxn=632.9, Pen=655.1, n=1563
  - Mid: R/P=1.167, Rxn=683.2, Pen=585.5, n=1578
  - High: R/P=1.135, Rxn=602.3, Pen=530.8, n=1560

### F25_BreakHistory [MODERATE]
- @30: spread=0.150, p=0.0276, d=0.113, best=Low, worst=Mid
  - Low: R/P=0.985, Rxn=102.7, Pen=104.2, n=1554
  - Mid: R/P=0.835, Rxn=91.4, Pen=109.4, n=1585
  - High: R/P=0.944, Rxn=95.1, Pen=100.7, n=1557
- @60: spread=0.181, p=0.0049, d=0.144, best=Low, worst=Mid
  - Low: R/P=1.055, Rxn=152.1, Pen=144.1, n=1554
  - Mid: R/P=0.874, Rxn=130.5, Pen=149.4, n=1585
  - High: R/P=0.910, Rxn=132.6, Pen=145.8, n=1557
- @120: spread=0.221, p=0.0000, d=0.191, best=Low, worst=Mid
  - Low: R/P=1.103, Rxn=220.1, Pen=199.6, n=1554
  - Mid: R/P=0.882, Rxn=183.8, Pen=208.4, n=1585
  - High: R/P=0.890, Rxn=185.7, Pen=208.5, n=1557
- @full: spread=0.496, p=0.0000, d=0.217, best=Low, worst=High
  - Low: R/P=1.362, Rxn=709.7, Pen=521.1, n=1554
  - Mid: R/P=1.084, Rxn=634.3, Pen=585.2, n=1585
  - High: R/P=0.865, Rxn=576.1, Pen=665.6, n=1557

### F11_DeltaDivergence [MODERATE]
- @30: spread=0.234, p=0.0000, d=0.144, best=Low, worst=High
  - Low: R/P=1.015, Rxn=100.6, Pen=99.1, n=1597
  - Mid: R/P=0.976, Rxn=100.2, Pen=102.6, n=1533
  - High: R/P=0.781, Rxn=88.1, Pen=112.8, n=1571
- @60: spread=0.177, p=0.0000, d=0.119, best=Low, worst=High
  - Low: R/P=1.020, Rxn=144.1, Pen=141.3, n=1597
  - Mid: R/P=0.976, Rxn=142.2, Pen=145.7, n=1533
  - High: R/P=0.843, Rxn=128.5, Pen=152.5, n=1571
- @120: spread=0.126, p=0.0018, d=0.090, best=Low, worst=High
  - Low: R/P=1.007, Rxn=202.6, Pen=201.3, n=1597
  - Mid: R/P=0.981, Rxn=199.5, Pen=203.4, n=1533
  - High: R/P=0.880, Rxn=186.6, Pen=212.0, n=1571
- @full: spread=0.009, p=0.6967, d=0.019, best=Mid, worst=Low
  - Low: R/P=1.080, Rxn=632.6, Pen=585.6, n=1597
  - Mid: R/P=1.089, Rxn=645.2, Pen=592.5, n=1533
  - High: R/P=1.081, Rxn=641.4, Pen=593.5, n=1571

### F23_CrossTFConfluence [MODERATE]
- @30: spread=0.105, p=0.0005, d=0.118, best=High, worst=Mid
  - Low: R/P=0.917, Rxn=95.7, Pen=104.5, n=1655
  - Mid: R/P=0.855, Rxn=90.3, Pen=105.6, n=1158
  - High: R/P=0.960, Rxn=100.4, Pen=104.6, n=1888
- @60: spread=0.160, p=0.0000, d=0.122, best=High, worst=Low
  - Low: R/P=0.874, Rxn=130.5, Pen=149.2, n=1655
  - Mid: R/P=0.903, Rxn=134.5, Pen=149.0, n=1158
  - High: R/P=1.035, Rxn=147.4, Pen=142.5, n=1888
- @120: spread=0.216, p=0.0000, d=0.152, best=High, worst=Low
  - Low: R/P=0.860, Rxn=182.5, Pen=212.1, n=1655
  - Mid: R/P=0.908, Rxn=193.6, Pen=213.1, n=1158
  - High: R/P=1.076, Rxn=210.0, Pen=195.2, n=1888
- @full: spread=0.465, p=0.0000, d=0.197, best=High, worst=Low
  - Low: R/P=0.849, Rxn=564.0, Pen=664.0, n=1655
  - Mid: R/P=1.121, Rxn=652.8, Pen=582.5, n=1158
  - High: R/P=1.314, Rxn=697.8, Pen=531.0, n=1888

### F06_ApproachVelocity [WEAK]
- @30: spread=0.097, p=1.0000, d=-0.188, best=Mid, worst=Low
  - Low: R/P=0.885, Rxn=106.9, Pen=120.7, n=1557
  - Mid: R/P=0.983, Rxn=87.3, Pen=88.8, n=1579
  - High: R/P=0.902, Rxn=94.8, Pen=105.2, n=1565
- @60: spread=0.115, p=0.9999, d=-0.161, best=Mid, worst=Low
  - Low: R/P=0.903, Rxn=152.7, Pen=169.1, n=1557
  - Mid: R/P=1.019, Rxn=128.5, Pen=126.2, n=1579
  - High: R/P=0.926, Rxn=133.7, Pen=144.5, n=1565
- @120: spread=0.126, p=0.9996, d=-0.158, best=Mid, worst=Low
  - Low: R/P=0.897, Rxn=213.1, Pen=237.5, n=1557
  - Mid: R/P=1.024, Rxn=182.8, Pen=178.6, n=1579
  - High: R/P=0.961, Rxn=193.2, Pen=201.0, n=1565
- @full: spread=0.240, p=1.0000, d=-0.173, best=Mid, worst=Low
  - Low: R/P=0.943, Rxn=679.3, Pen=720.1, n=1557
  - Mid: R/P=1.183, Rxn=571.6, Pen=483.2, n=1579
  - High: R/P=1.174, Rxn=668.8, Pen=569.8, n=1565

### F02_ZoneWidth [WEAK]
- @30: spread=0.076, p=0.9992, d=-0.126, best=Low, worst=High
  - Low: R/P=0.950, Rxn=89.9, Pen=94.7, n=1599
  - Mid: R/P=0.940, Rxn=97.0, Pen=103.3, n=1542
  - High: R/P=0.874, Rxn=102.0, Pen=116.7, n=1560
- @60: spread=0.112, p=0.6887, d=-0.010, best=Mid, worst=High
  - Low: R/P=0.942, Rxn=126.4, Pen=134.3, n=1599
  - Mid: R/P=1.005, Rxn=143.6, Pen=142.9, n=1542
  - High: R/P=0.893, Rxn=145.1, Pen=162.5, n=1560
- @120: spread=0.146, p=0.7407, d=-0.010, best=Mid, worst=High
  - Low: R/P=0.945, Rxn=177.8, Pen=188.2, n=1599
  - Mid: R/P=1.039, Rxn=204.9, Pen=197.2, n=1542
  - High: R/P=0.892, Rxn=206.7, Pen=231.6, n=1560
- @full: spread=0.216, p=0.0000, d=0.287, best=High, worst=Low
  - Low: R/P=1.006, Rxn=539.5, Pen=536.2, n=1599
  - Mid: R/P=1.017, Rxn=642.6, Pen=631.8, n=1542
  - High: R/P=1.222, Rxn=739.4, Pen=605.3, n=1560

### F09_ZW_ATR [MODERATE]
- @30: spread=0.126, p=0.0000, d=0.202, best=Low, worst=High
  - Low: R/P=0.962, Rxn=106.6, Pen=110.8, n=1552
  - Mid: R/P=0.955, Rxn=94.8, Pen=99.2, n=1597
  - High: R/P=0.836, Rxn=87.5, Pen=104.6, n=1552
- @60: spread=0.092, p=0.0000, d=0.158, best=Low, worst=High
  - Low: R/P=0.978, Rxn=151.3, Pen=154.8, n=1552
  - Mid: R/P=0.967, Rxn=135.0, Pen=139.7, n=1597
  - High: R/P=0.886, Rxn=128.6, Pen=145.1, n=1552
- @120: spread=0.076, p=0.0016, d=0.124, best=Low, worst=High
  - Low: R/P=0.981, Rxn=211.6, Pen=215.7, n=1552
  - Mid: R/P=0.978, Rxn=189.5, Pen=193.7, n=1597
  - High: R/P=0.905, Rxn=187.9, Pen=207.7, n=1552
- @full: spread=0.200, p=0.5187, d=0.038, best=High, worst=Low
  - Low: R/P=0.975, Rxn=619.0, Pen=635.0, n=1552
  - Mid: R/P=1.114, Rxn=654.9, Pen=587.9, n=1597
  - High: R/P=1.175, Rxn=644.5, Pen=548.7, n=1552

### F22_RecentBreakRate [WEAK]
- @30: spread=0.016, p=0.0000, d=0.272, best=High, worst=Low
  - Low: R/P=0.907, Rxn=81.3, Pen=89.6, n=1552
  - Mid: R/P=0.922, Rxn=102.0, Pen=110.6, n=1595
  - High: R/P=0.924, Rxn=105.4, Pen=114.2, n=1554
- @60: spread=0.070, p=1.0000, d=-0.192, best=Low, worst=High
  - Low: R/P=0.979, Rxn=122.0, Pen=124.5, n=1552
  - Mid: R/P=0.952, Rxn=146.5, Pen=153.9, n=1595
  - High: R/P=0.909, Rxn=146.1, Pen=160.7, n=1554
- @120: spread=0.117, p=0.9999, d=-0.133, best=Low, worst=High
  - Low: R/P=1.029, Rxn=180.5, Pen=175.5, n=1552
  - Mid: R/P=0.940, Rxn=204.4, Pen=217.4, n=1595
  - High: R/P=0.912, Rxn=203.7, Pen=223.4, n=1554
- @full: spread=0.124, p=0.9966, d=-0.045, best=Mid, worst=High
  - Low: R/P=1.113, Rxn=506.8, Pen=455.3, n=1552
  - Mid: R/P=1.139, Rxn=689.4, Pen=605.3, n=1595
  - High: R/P=1.015, Rxn=721.2, Pen=710.3, n=1554

### F15_ZZSwingRegime [WEAK]
- @30: spread=0.061, p=0.0065, d=0.091, best=High, worst=Mid
  - Low: R/P=0.918, Rxn=103.2, Pen=112.4, n=1592
  - Mid: R/P=0.879, Rxn=87.7, Pen=99.7, n=1083
  - High: R/P=0.940, Rxn=95.5, Pen=101.6, n=2025
- @60: spread=0.069, p=0.6996, d=-0.024, best=High, worst=Low
  - Low: R/P=0.912, Rxn=143.1, Pen=157.0, n=1592
  - Mid: R/P=0.928, Rxn=128.8, Pen=138.8, n=1083
  - High: R/P=0.980, Rxn=139.5, Pen=142.3, n=2025
- @120: spread=0.070, p=0.9896, d=-0.101, best=Mid, worst=Low
  - Low: R/P=0.918, Rxn=204.3, Pen=222.6, n=1592
  - Mid: R/P=0.988, Rxn=185.9, Pen=188.1, n=1083
  - High: R/P=0.970, Rxn=195.6, Pen=201.5, n=2025
- @full: spread=0.088, p=0.9434, d=-0.031, best=High, worst=Low
  - Low: R/P=1.030, Rxn=667.9, Pen=648.2, n=1592
  - Mid: R/P=1.107, Rxn=585.9, Pen=529.3, n=1083
  - High: R/P=1.118, Rxn=646.4, Pen=578.0, n=2025

### F14_AvgOrderSize [WEAK]
- @30: spread=0.029, p=0.2913, d=-0.020, best=High, worst=Mid
  - Low: R/P=0.922, Rxn=95.7, Pen=103.8, n=1690
  - Mid: R/P=0.901, Rxn=97.7, Pen=108.4, n=1379
  - High: R/P=0.930, Rxn=95.7, Pen=102.9, n=1632
- @60: spread=0.067, p=0.1973, d=0.008, best=High, worst=Mid
  - Low: R/P=0.923, Rxn=136.2, Pen=147.5, n=1690
  - Mid: R/P=0.920, Rxn=138.8, Pen=150.8, n=1379
  - High: R/P=0.987, Rxn=140.0, Pen=141.8, n=1632
- @120: spread=0.039, p=0.6066, d=-0.001, best=High, worst=Mid
  - Low: R/P=0.959, Rxn=196.4, Pen=204.7, n=1690
  - Mid: R/P=0.931, Rxn=196.3, Pen=210.7, n=1379
  - High: R/P=0.971, Rxn=196.1, Pen=202.1, n=1632
- @full: spread=0.059, p=0.0450, d=0.022, best=Low, worst=Mid
  - Low: R/P=1.117, Rxn=658.5, Pen=589.4, n=1690
  - Mid: R/P=1.058, Rxn=643.8, Pen=608.2, n=1379
  - High: R/P=1.069, Rxn=616.6, Pen=576.6, n=1632

### F17_ATRRegime [MODERATE]
- @30: spread=0.031, p=0.0005, d=0.144, best=High, worst=Mid
  - Low: R/P=0.913, Rxn=84.3, Pen=92.3, n=1557
  - Mid: R/P=0.905, Rxn=94.5, Pen=104.5, n=1586
  - High: R/P=0.936, Rxn=110.1, Pen=117.7, n=1557
- @60: spread=0.054, p=0.0004, d=0.159, best=High, worst=Mid
  - Low: R/P=0.955, Rxn=123.1, Pen=128.9, n=1557
  - Mid: R/P=0.912, Rxn=133.7, Pen=146.7, n=1586
  - High: R/P=0.965, Rxn=158.2, Pen=163.8, n=1557
- @120: spread=0.105, p=0.9017, d=-0.042, best=Low, worst=Mid
  - Low: R/P=1.005, Rxn=179.7, Pen=178.9, n=1557
  - Mid: R/P=0.900, Rxn=186.6, Pen=207.4, n=1586
  - High: R/P=0.966, Rxn=222.7, Pen=230.4, n=1557
- @full: spread=0.115, p=0.6579, d=0.022, best=Low, worst=Mid
  - Low: R/P=1.161, Rxn=665.0, Pen=572.9, n=1557
  - Mid: R/P=1.046, Rxn=649.8, Pen=621.3, n=1586
  - High: R/P=1.047, Rxn=604.2, Pen=576.9, n=1557

### F07_Deceleration [WEAK]
- @30: spread=0.035, p=0.4881, d=0.015, best=Low, worst=High
  - Low: R/P=0.933, Rxn=97.3, Pen=104.3, n=1551
  - Mid: R/P=0.925, Rxn=95.8, Pen=103.7, n=1598
  - High: R/P=0.899, Rxn=95.7, Pen=106.6, n=1551
- @60: spread=0.051, p=0.6220, d=0.012, best=Low, worst=High
  - Low: R/P=0.971, Rxn=140.8, Pen=145.0, n=1551
  - Mid: R/P=0.943, Rxn=135.2, Pen=143.4, n=1598
  - High: R/P=0.920, Rxn=139.0, Pen=151.1, n=1551
- @120: spread=0.050, p=0.2402, d=-0.004, best=Mid, worst=High
  - Low: R/P=0.956, Rxn=195.2, Pen=204.2, n=1551
  - Mid: R/P=0.980, Rxn=196.5, Pen=200.5, n=1598
  - High: R/P=0.930, Rxn=197.2, Pen=212.1, n=1551
- @full: spread=0.047, p=0.0307, d=0.050, best=High, worst=Low
  - Low: R/P=1.060, Rxn=621.9, Pen=586.4, n=1551
  - Mid: R/P=1.081, Rxn=641.2, Pen=592.9, n=1598
  - High: R/P=1.108, Rxn=656.1, Pen=592.2, n=1551

### F19_VPConsumption [MODERATE]
- @30: spread=0.010, p=0.0000, d=0.160, best=VP_RAY_INTACT, worst=VP_RAY_CONSUMED
  - VP_RAY_INTACT: R/P=0.921, Rxn=100.8, Pen=109.5, n=3297
  - VP_RAY_CONSUMED: R/P=0.911, Rxn=85.6, Pen=94.0, n=1404
- @60: spread=0.019, p=0.0000, d=0.188, best=VP_RAY_INTACT, worst=VP_RAY_CONSUMED
  - VP_RAY_INTACT: R/P=0.949, Rxn=145.7, Pen=153.6, n=3297
  - VP_RAY_CONSUMED: R/P=0.930, Rxn=120.7, Pen=129.8, n=1404
- @120: spread=0.001, p=0.0000, d=0.176, best=VP_RAY_INTACT, worst=VP_RAY_CONSUMED
  - VP_RAY_INTACT: R/P=0.955, Rxn=205.6, Pen=215.3, n=3297
  - VP_RAY_CONSUMED: R/P=0.954, Rxn=174.3, Pen=182.7, n=1404
- @full: spread=0.256, p=1.0000, d=-0.006, best=VP_RAY_CONSUMED, worst=VP_RAY_INTACT
  - VP_RAY_INTACT: R/P=1.018, Rxn=641.0, Pen=629.3, n=3297
  - VP_RAY_CONSUMED: R/P=1.275, Rxn=636.6, Pen=499.3, n=1404

### F08_PriorRxnSpeed [MODERATE]
- @30: spread=0.102, p=0.0000, d=0.338, best=High, worst=Mid
  - Low: R/P=0.809, Rxn=75.9, Pen=93.8, n=1015
  - Mid: R/P=0.799, Rxn=81.1, Pen=101.4, n=1016
  - High: R/P=0.902, Rxn=110.3, Pen=122.4, n=1008
- @60: spread=0.012, p=0.0000, d=0.320, best=High, worst=Low
  - Low: R/P=0.853, Rxn=112.8, Pen=132.3, n=1015
  - Mid: R/P=0.855, Rxn=118.2, Pen=138.3, n=1016
  - High: R/P=0.865, Rxn=149.4, Pen=172.8, n=1008
- @120: spread=0.083, p=1.0000, d=-0.226, best=Low, worst=High
  - Low: R/P=0.901, Rxn=166.9, Pen=185.2, n=1015
  - Mid: R/P=0.889, Rxn=172.9, Pen=194.5, n=1016
  - High: R/P=0.818, Rxn=203.2, Pen=248.4, n=1008
- @full: spread=0.166, p=1.0000, d=-0.245, best=Low, worst=High
  - Low: R/P=1.163, Rxn=572.5, Pen=492.2, n=1015
  - Mid: R/P=1.122, Rxn=610.1, Pen=543.6, n=1016
  - High: R/P=0.997, Rxn=744.7, Pen=746.7, n=1008