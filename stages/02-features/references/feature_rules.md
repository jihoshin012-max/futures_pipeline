---
last_reviewed: 2026-03-14
---

# Feature Rules

Stage 02 agent reads this file before each experiment.

**Rule 1 — Entry-time only (Pipeline Rule 3):** Feature must be computable at entry bar close. No lookahead.
**Rule 2 — Registered sources only:** Use source_id values from shared/data_registry.md. No ad-hoc data reads.
**Rule 3 — Keep threshold:** Spread > 0.15 AND Mann-Whitney U p < 0.10. Both must pass to keep a feature.
**Rule 4 — One feature per experiment:** Edit exactly one file per autoresearch loop iteration.
**Rule 5 — Register before use:** Add feature to shared/feature_definitions.md before referencing it in any script.

See: shared/feature_definitions.md
