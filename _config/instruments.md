# Instrument Registry
last_reviewed: 2026-03-13
## THE RULE
Every instrument-specific constant must be read from this file.
No pipeline script may hardcode tick size, dollar value, session times, or cost_ticks.

## Registered Instruments

### NQ
- Symbol: NQ (CME E-mini NASDAQ-100)
- Tick size: 0.25 points
- Tick value: $5.00
- Session: RTH 09:30–16:15 ET | ETH 18:00–09:30 ET
- Cost model (round trip): 3 ticks = $15.00 (conservative default; user actual ~1 tick = $5/RT. P1b validation runs at cost_ticks=1)
- Bar data prefix: NQ_BarData
- Margin: check current at CME (varies)

### ES
- Symbol: ES (CME E-mini S&P 500)
- Tick size: 0.25 points
- Tick value: $12.50
- Session: RTH 09:30–16:15 ET | ETH 18:00–09:30 ET
- Cost model (round trip): 1 tick = $12.50
- Bar data prefix: ES_BarData
- Margin: check current at CME (varies)

### GC
- Symbol: GC (CME Gold Futures)
- Tick size: 0.10 points
- Tick value: $10.00
- Session: 18:00–17:00 ET (nearly 24hr, Sunday–Friday)
- Cost model (round trip): 2 ticks = $20.00
- Bar data prefix: GC_BarData
- Margin: check current at CME (varies)

## To Add a New Instrument
1. Add a block above following the template
2. Add bar data files to 01-data/data/bar_data/
3. Re-run Stage 01 validation
Cost model values require human approval — changing them affects all historical PF calculations.

## Template for new instrument
### {SYMBOL}
- Symbol: {SYMBOL} ({exchange} {full name})
- Tick size: {N} points
- Tick value: ${N}
- Session: {session hours}
- Cost model (round trip): {N} ticks = ${N}
- Bar data prefix: {SYMBOL}_BarData
- Margin: check current at {exchange} (varies)
