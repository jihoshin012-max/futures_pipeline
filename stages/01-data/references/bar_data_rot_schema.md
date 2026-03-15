# Bar Data Rotational Schema
last_reviewed: 2026-03-14
# Required columns for rotational bar data files (250-vol, 250-tick, 10-sec).
# Source IDs: bar_data_250vol_rot, bar_data_250tick_rot, bar_data_10sec_rot — all share this 35-column schema.
# Bar type encoded in filename; files live in bar_data/{volume,tick,time}/ respectively.

## Raw Header (35 columns, comma-separated)
Date, Time, Open, High, Low, Last, Volume, # of Trades, OHLC Avg, HLC Avg, HL Avg, Bid Volume, Ask Volume, Zig Zag, Text Labels, Reversal Price, Zig Zag Line Length, Zig Zag Num Bars, Zig Zag Mid-Point, Extension Lines, Zig Zag Oscillator, Sum, Top, Bottom, Top MovAvg, Bottom MovAvg, Top, Bottom, Top MovAvg, Bottom MovAvg, Top, Bottom, Top MovAvg, Bottom MovAvg, ATR

## Column Index Table

| Index | Raw Header Name      | Alias / Disambiguation   | Type   | Description |
|-------|----------------------|--------------------------|--------|-------------|
| 0     | Date                 | Date                     | str    | Bar date in M/D/YYYY format (e.g. 9/21/2025) |
| 1     | Time                 | Time                     | str    | Bar time in H:MM (e.g. 18:00) |
| 2     | Open                 | Open                     | float  | Bar open price |
| 3     | High                 | High                     | float  | Bar high price |
| 4     | Low                  | Low                      | float  | Bar low price |
| 5     | Last                 | Last (Close)             | float  | Bar close/last price |
| 6     | Volume               | Volume                   | int    | Bar volume (contracts traded) |
| 7     | # of Trades          | NumTrades                | int    | Number of individual trades in bar |
| 8     | OHLC Avg             | OHLC_Avg                 | float  | Average of Open, High, Low, Close |
| 9     | HLC Avg              | HLC_Avg                  | float  | Average of High, Low, Close |
| 10    | HL Avg               | HL_Avg                   | float  | Average of High and Low (midpoint) |
| 11    | Bid Volume           | BidVolume                | int    | Volume traded at bid |
| 12    | Ask Volume           | AskVolume                | int    | Volume traded at ask |
| 13    | Zig Zag              | ZigZag                   | float  | Zig Zag indicator value |
| 14    | Text Labels          | TextLabels               | str    | NinjaTrader text label (usually empty) |
| 15    | Reversal Price       | ReversalPrice            | float  | Zig Zag reversal price |
| 16    | Zig Zag Line Length  | ZigZagLineLength         | float  | Length of current zig-zag leg |
| 17    | Zig Zag Num Bars     | ZigZagNumBars            | int    | Number of bars in current zig-zag leg |
| 18    | Zig Zag Mid-Point    | ZigZagMidPoint           | float  | Midpoint price of current zig-zag leg |
| 19    | Extension Lines      | ExtensionLines           | float  | Zig Zag extension line value |
| 20    | Zig Zag Oscillator   | ZigZagOscillator         | float  | Zig Zag oscillator value |
| 21    | Sum                  | Sum                      | float  | Summation of Study Subgraph - Periodic (SC ID:3). Input to all 3 StdDev bands |
| 22    | Top                  | StdDev_1_Top             | float  | StdDev Bands ID:4 — upper band (Length=500, Mult=1.5, WMA) |
| 23    | Bottom               | StdDev_1_Bottom          | float  | StdDev Bands ID:4 — lower band |
| 24    | Top MovAvg           | StdDev_1_TopMA           | float  | StdDev Bands ID:4 — upper moving average |
| 25    | Bottom MovAvg        | StdDev_1_BottomMA        | float  | StdDev Bands ID:4 — lower moving average |
| 26    | Top                  | StdDev_2_Top             | float  | StdDev Bands ID:5 — upper band (Length=500, Mult=4.0, WMA) |
| 27    | Bottom               | StdDev_2_Bottom          | float  | StdDev Bands ID:5 — lower band |
| 28    | Top MovAvg           | StdDev_2_TopMA           | float  | StdDev Bands ID:5 — upper moving average |
| 29    | Bottom MovAvg        | StdDev_2_BottomMA        | float  | StdDev Bands ID:5 — lower moving average |
| 30    | Top                  | StdDev_3_Top             | float  | StdDev Bands ID:6 — upper band (Length=5000, Mult=4.0, EMA) — hidden/structural |
| 31    | Bottom               | StdDev_3_Bottom          | float  | StdDev Bands ID:6 — lower band — hidden/structural |
| 32    | Top MovAvg           | StdDev_3_TopMA           | float  | StdDev Bands ID:6 — upper moving average |
| 33    | Bottom MovAvg        | StdDev_3_BottomMA        | float  | StdDev Bands ID:6 — lower moving average |
| 34    | ATR                  | ATR                      | float  | Average True Range (SC ID:13) |

## Sierra Chart Study Stack (source of cols 13-34)

| SC ID | Study | Cols | Parameters |
|-------|-------|------|------------|
| 1 | Zig Zag | 13-20 | — |
| 3 | Summation of Study Subgraph - Periodic | 21 | Input to all StdDev bands |
| 4 | Standard Deviation Bands | 22-25 | Length=500, Mult=1.5, WMA, visible (blue) |
| 5 | Standard Deviation Bands | 26-29 | Length=500, Mult=4.0, WMA, visible (red) |
| 6 | Standard Deviation Bands (Hidden) | 30-33 | Length=5000, Mult=4.0, EMA, structural |
| 13 | ATR | 34 | — |
| 7 | ATEAM Rotation V1 OG | — | Trading system, no subgraph export |
| 2 | ATEAM CSV Export | — | Export script |
| 11-12 | Color Background alerts | — | Not exported |

## Duplicate Column Name Disambiguation
The raw header contains duplicate names for columns 22-33:
- "Top" appears at indices 22, 26, 30 → StdDev_1_Top, StdDev_2_Top, StdDev_3_Top
- "Bottom" appears at indices 23, 27, 31 → StdDev_1_Bottom, StdDev_2_Bottom, StdDev_3_Bottom
- "Top MovAvg" appears at indices 24, 28, 32 → StdDev_1_TopMA, StdDev_2_TopMA, StdDev_3_TopMA
- "Bottom MovAvg" appears at indices 25, 29, 33 → StdDev_1_BottomMA, StdDev_2_BottomMA, StdDev_3_BottomMA

When loading with pandas, use `header=0` and then rename by positional index, not by column name,
to correctly disambiguate. Pandas will auto-suffix duplicates as ".1" and ".2" if not renamed manually.

## Required Columns (minimum for validation)
Date, Time, Open, High, Low, Last, Volume

## Notes
- Date format: M/D/YYYY (e.g. "9/21/2025") — not ISO format
- Time format: H:MM (e.g. "18:00", "9:30")
- P1 data starts 2025-09-21 (rotational archetype boundary)
- P2 data ends 2026-03-13 (rotational archetype boundary)
- bar_data_250vol_rot, bar_data_250tick_rot, and bar_data_10sec_rot all share this exact schema
- Files stored in: stages/01-data/data/bar_data/{volume,tick,time}/ respectively
