---
last_reviewed: 2026-03-14
---

# Feature Definitions

**PIPELINE RULE 3 (Entry-time only):** Every feature MUST be computable from data available at bar close before entry. No lookahead. Violation = disqualification.

This file starts empty. Stage 02 autoresearch registers new features here before using them.

## Registered Features

(empty)

## Template for New Features

Copy this block when registering a new feature:

```
### {feature_name}

- Source: {source_id from data_registry.md}
- Computation: {formula or method; no future data}
- Bin edges: [x1, x2] (defines low/mid/high buckets)
- Entry-time computable: YES  # must be YES — NO = rejected
- Used by: {archetype list}
```
