# Zone Touch Strategy — ACSIL Study Chain Reference

## Why multiple studies exist

The zone touch strategy requires 4 separate ACSIL studies working together. Each handles a different stage of the data pipeline. They must stay version-locked — if any one changes, the data changes and pipeline results are invalidated.

## The chain

### 1. SupplyDemandZonesV4 (V4)
**What it does:** Creates supply/demand zones on the chart in real-time. Detects when price forms a zone structure (rally-base-rally, drop-base-drop, etc.) and draws the zone.

**Why it's needed:** This is the foundation — no zones, no strategy. Every zone the autotrader trades was created by this study.

**Live vs History:** This is the LIVE version. It runs on chart continuously, creating and managing zones as new bars form.

**Input settings:** See v4_study_settings_[TF].txt — one per timeframe. These control zone detection thresholds, minimum width rules, and structure parameters.

### 2. SupplyDemandZonesV4_history (V4_history)
**What it does:** Exports the complete historical record of all zones — including Same-Bar-Break (SBB) zones that V4 live creates and immediately destroys within a single bar.

**Why it's needed:** SBB zones are invisible to V4 live (they exist for less than one bar) but they matter for data quality. The clean-data pipeline rebuild (v3.1) used V4_history to capture all 1,411 SBB touches that V4 live would miss. Without this, 34% of the touch population is invisible.

**Why separate from V4:** V4 live manages zones for real-time trading. V4_history is a batch export tool for backtesting — it replays history and captures every zone that ever existed, including ephemeral ones.

### 3. ZoneReactionAnalyzer (ZRA)
**What it does:** Detects when price touches a zone and records the touch event with metadata: TouchType (DEMAND_EDGE, SUPPLY_EDGE), TouchSequence, Penetration, Reaction, ZoneWidth, CascadeState, SourceLabel, ZoneAgeBars, and all other fields the scoring model needs.

**Why it's needed:** V4 creates zones but doesn't track what happens when price returns to them. ZRA is the measurement tool — it watches for touches and records the outcome. The entire feature set (F10, F04, F01, F21) is computed from ZRA's output.

**Input settings:** See zra_study_settings.txt. Controls touch detection thresholds and which touch types are recorded.

### 4. ZoneBounceSignalsV4_aligned (ZB4)
**What it does:** Aligns ZRA touch detection with V4 zone boundaries to ensure 100% edge touch match rate. Verified at 100% match (1487/1487 touches) on full recalculation (2026-03-07 audit).

**Why it's needed:** V4 and ZRA can drift slightly in how they define zone edges (floating point, bar timing). ZB4 ensures that when ZRA says "DEMAND_EDGE touch at 24850.0", V4 agrees that 24850.0 is the demand zone bottom. Without alignment, some touches would score against the wrong zone.

**Input settings:** See zb4_study_settings.txt. Controls alignment tolerances.

## The autotrader's role

### 5. ATEAM_ZONE_BOUNCE_V1 (new — built from Part A spec)
**What it does:** Reads zone touch events (from V4/ZRA), computes the A-Cal score using 4 features, routes to CT or WT/NT mode, and manages 2-leg exits.

**Why it's separate:** The autotrader consumes zone data — it doesn't create or measure zones. Keeping it separate means V4/ZRA can be updated independently (with re-validation) without touching trading logic, and vice versa.

## Version lock rule

All studies and config files in this directory are snapshots from 2026-03-22. They produced the data that Pipeline v3.1 validated. If you modify any study in C:\Projects\sierrachart\, the pipeline results may no longer be valid. Before deploying a modified study:
1. Re-export data with the modified study
2. Re-run at minimum Prompt 0 (baseline) to check for data drift
3. If baseline changes materially, re-run full pipeline

## Files in this directory

| File | Study | Snapshot Date | Notes |
|------|-------|--------------|-------|
| SupplyDemandZonesV4.cpp | V4 | 2026-03-22 | Live zone creation (compiled Mar 8) |
| SupplyDemandZonesV4_history.cpp | V4_history | 2026-03-22 | SBB zone export (compiled Mar 18) |
| ZoneReactionAnalyzer.cpp | ZRA | 2026-03-22 | Touch detection (compiled Mar 7) |
| ZoneBounceSignalsV4_aligned.cpp | ZB4 | 2026-03-22 | Edge alignment (compiled Mar 20) |
| zone_bounce_config.h | Header | 2026-03-22 | P1-frozen config shared by autotrader |
| ATEAM_ZONE_BOUNCE_V1.cpp | Autotrader | 2026-03-22 | Zone bounce autotrader (Part A spec) |
| scoring_model_acal.json | Config | 2026-03-22 | P1-frozen A-Cal weights + threshold |
| feature_config.json | Config | 2026-03-22 | P1-frozen bin edges + trend cutoffs |
| v4_study_settings_15m.txt | Settings | — | V4 inputs for 15m (PENDING — export from SC) |
| v4_study_settings_30m.txt | Settings | — | V4 inputs for 30m (PENDING — export from SC) |
| v4_study_settings_60m.txt | Settings | — | V4 inputs for 60m (PENDING — export from SC) |
| v4_study_settings_90m.txt | Settings | — | V4 inputs for 90m (PENDING — export from SC) |
| v4_study_settings_120m.txt | Settings | — | V4 inputs for 120m (PENDING — export from SC) |
| zra_study_settings.txt | Settings | — | ZRA inputs (PENDING — export from SC) |
| zb4_study_settings.txt | Settings | — | ZB4 inputs (PENDING — export from SC) |
