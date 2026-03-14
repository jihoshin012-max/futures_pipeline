# Stage 02 Feature Engineering — Program
# Max 30 lines (machine-readable fields must stay at top)

## Direction
Add features to feature_engine.py that predict trade outcomes at entry time.
Start with bar-derived features (ATR, volume ratios, momentum) — zone_width is already seeded.
Each experiment: add or modify ONE feature in compute_features().

## Machine-Readable Fields
METRIC: spread
KEEP RULE: 0.15
BUDGET: 300
NEW_FEATURE: zone_width

## Constraints
- Every feature must be entry-time computable (bar_df is truncated at BarIndex)
- Do not read Reaction, Penetration, RxnBar_*, PenBar_* from touch_row — they are post-entry
- One feature change per experiment
- Read feature_rules.md before adding any feature
