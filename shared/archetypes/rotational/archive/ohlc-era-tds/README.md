# TDS Profiles — Archived (OHLC Era)

TDS not applicable to tick-data V1.1 candidates:

- **L1 (velocity step-widening)** is redundant — ATR-normalization already adapts
  distances to volatility. When ATR rises, reversal and add distances widen
  automatically. No need for a separate detector.

- **L2 (refuse adds)** is irrelevant at MTP=0 — no adds are ever refused because
  there is no position cap to trigger refusal.

- **L3 (force flatten / drawdown budget)** is harmful — Test D (2026-03-17) proved
  all hard stop thresholds hurt PF on tick data. ATR-normalized stops at 2.0x, 3.0x,
  4.0x, and 5.0x ATR all produced worse results than the uncapped baseline.

These TDS configs were last calibrated on OHLC threshold-crossing data for
MAX_PROFIT SD=6.0/ML=1/MTP=8 — that config is no longer a candidate.

If V2 MTP=2 walking is ever deployed, TDS re-calibration on tick data would be needed.
