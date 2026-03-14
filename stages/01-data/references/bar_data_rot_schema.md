# Bar Data Rotational Schema
last_reviewed: 2026-03-14
# Required columns for {SYMBOL}_BarData_250vol_rot_* and {SYMBOL}_BarData_250tick_rot_* files.
# Source IDs: bar_data_250vol_rot, bar_data_250tick_rot — both share this 35-column schema.
# Bar type: Volume bars (250-vol) or Tick bars (250-tick); encoded in filename.
# Files live in: stages/01-data/data/bar_data/volume/ (all 4 rotational files are here)

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
| 21    | Sum                  | Sum                      | float  | Sum indicator value |
| 22    | Top                  | Channel_1_Top            | float  | Channel/band study 1 — upper boundary |
| 23    | Bottom               | Channel_1_Bottom         | float  | Channel/band study 1 — lower boundary |
| 24    | Top MovAvg           | Channel_1_TopMovAvg      | float  | Channel/band study 1 — upper moving average |
| 25    | Bottom MovAvg        | Channel_1_BottomMovAvg   | float  | Channel/band study 1 — lower moving average |
| 26    | Top                  | Channel_2_Top            | float  | Channel/band study 2 — upper boundary |
| 27    | Bottom               | Channel_2_Bottom         | float  | Channel/band study 2 — lower boundary |
| 28    | Top MovAvg           | Channel_2_TopMovAvg      | float  | Channel/band study 2 — upper moving average |
| 29    | Bottom MovAvg        | Channel_2_BottomMovAvg   | float  | Channel/band study 2 — lower moving average |
| 30    | Top                  | Channel_3_Top            | float  | Channel/band study 3 — upper boundary |
| 31    | Bottom               | Channel_3_Bottom         | float  | Channel/band study 3 — lower boundary |
| 32    | Top MovAvg           | Channel_3_TopMovAvg      | float  | Channel/band study 3 — upper moving average |
| 33    | Bottom MovAvg        | Channel_3_BottomMovAvg   | float  | Channel/band study 3 — lower moving average |
| 34    | ATR                  | ATR                      | float  | Average True Range |

## Duplicate Column Name Disambiguation
The raw header contains duplicate names for columns 22-33:
- "Top" appears at indices 22, 26, 30 → Channel_1_Top, Channel_2_Top, Channel_3_Top
- "Bottom" appears at indices 23, 27, 31 → Channel_1_Bottom, Channel_2_Bottom, Channel_3_Bottom
- "Top MovAvg" appears at indices 24, 28, 32 → Channel_1_TopMovAvg, Channel_2_TopMovAvg, Channel_3_TopMovAvg
- "Bottom MovAvg" appears at indices 25, 29, 33 → Channel_1_BottomMovAvg, Channel_2_BottomMovAvg, Channel_3_BottomMovAvg

When loading with pandas, use `header=0` and then rename by positional index, not by column name,
to correctly disambiguate. Pandas will auto-suffix duplicates as ".1" and ".2" if not renamed manually.

## Required Columns (minimum for validation)
Date, Time, Open, High, Low, Last, Volume

## Notes
- Date format: M/D/YYYY (e.g. "9/21/2025") — not ISO format
- Time format: H:MM (e.g. "18:00", "9:30")
- P1 data starts 2025-09-21 (rotational archetype boundary)
- P2 data ends 2026-03-13 (rotational archetype boundary)
- Both bar_data_250vol_rot and bar_data_250tick_rot share this exact schema
- Files currently stored in: stages/01-data/data/bar_data/volume/ (both vol and tick rotational files)
