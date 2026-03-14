---
last_reviewed: 2026-03-13
reviewed_by: Ji
---
# Stage 06: Deployment Builder
## YOUR TASK: Assemble context package for ACSIL generation. Human fires the prompt.
## CONSTRAINT: Human must create deployment_ready.flag. You never create it.

| | |
|---|---|
| **Inputs** | 04-backtest/output/frozen_params.json, shared/scoring_models/, shared/feature_definitions.md |
| **Process** | Run assemble_context.sh -> human fires Claude Code prompt -> human compiles + verifies |
| **Outputs** | output/{strategy_id}/*.cpp, output/{strategy_id}/deployment_checklist.md |
| **Human gate** | Compile, verify on replay, create deployment_ready.flag |

## WHAT THIS STAGE IS
Context assembly. The pipeline gathers everything Claude Code needs in one place.
Human fires the generation prompt. Human reviews .cpp output. Human compiles and verifies.
No automated tests. No templates required. Output file count determined by Claude Code.

## DEPLOYMENT CHECKLIST (human completes — do not skip)
- [ ] assemble_context.sh run — context_package.md reviewed for completeness
- [ ] Claude Code generation prompt fired with context_package.md loaded
- [ ] Generated .cpp file(s) reviewed — no magic numbers, params match frozen_params.json
- [ ] Compiled in Sierra Chart without warnings
- [ ] Replay verification: entries match expected signals on known dates
- [ ] audit/audit_entry.sh deploy invoked
- [ ] deployment_ready.flag created
