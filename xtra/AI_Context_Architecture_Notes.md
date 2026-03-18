# AI Context Architecture & Tooling Notes
last_reviewed: 2026-03-15
status: living document — revisit after rotational archetype and/or dashboard milestone

## Purpose

Capture ongoing thinking about how this pipeline manages AI context, when to adopt structural tooling, and the modular context architecture that drives the workflow. Intended as a decision reference once the codebase crosses complexity thresholds.

---

## 1. Modular Context Architecture (Current System)

### Core Pattern
- CLAUDE.md stays minimal — routes to other files, doesn't hold content
- Separate .md files for rules, context, how-tos — loaded only when relevant
- SOPs created in-the-moment when Claude does something well (encode tested patterns, not hypothetical ones)
- Learnings constantly fed back into core files (lessons.md, CONTEXT.md updates, config refinements)

### Why It Works
- **Respects LLM attention:** Small focused files load near the top of context window; avoids lost-in-middle problem with monolithic configs
- **Empirically grown:** Every SOP reflects a validated workflow, not a pre-built guess
- **Feedback loop is the moat:** System gets smarter through use — corrections become lessons, good runs become SOPs. Can't drift from reality because reality wrote it.
- **Zero dependencies:** No plugins, no external tooling, no 500-line config files. Unix philosophy applied to AI context management — small sharp files that compose.

### Current Implementation in This Pipeline
| File/Pattern | Role |
|---|---|
| CLAUDE.md (60 lines) | Router — points to stage CONTEXT.md files |
| CONTEXT.md per stage | Loaded only when agent works in that stage |
| _config/*.md | Instrument constants, statistical gates, periods — on-demand reference |
| program.md | Steers autoresearch loops, editable between runs |
| lessons.md | Feedback loop persisting across sessions |

### Known Limits
- **Bottlenecked by operator discipline** — if you stop feeding learnings back, it stops improving. No passive improvement mechanism.
- **Transfer is hard** — handing to someone else gives them files but not the instinct for when to create/update them.
- **Discovery isn't built in** — you must know a context file exists to load it. At scale, CLAUDE.md becomes a routing problem itself. Keep it a clean index.

---

## 2. Tool Evaluation Summary (Ordered by Immediate Relevance)

### Tier 0 — Adopt Now (Immediate ROI)

#### RTK (Token Compression)
- **What:** Rust CLI proxy that compresses shell command output before it hits LLM context. `git status` → `rtk git status`, transparently via auto-rewrite hook. Single binary, zero dependencies, <10ms overhead.
- **Why it matters:** Autoresearch sessions run hundreds of experiments generating git ops, test output, and directory listings — all burning context tokens. RTK claims 60-90% compression on shell output. The `rtk gain` command provides analytics on actual token savings per session.
- **Adopt when:** Now — install, run one autoresearch session, check `rtk gain` to see if the savings are material.
- **Caveat:** Only compresses shell command output, not file reads or data file content. If your token pressure comes from reading large JSONs/CSVs, RTK won't help there. But it's zero-risk to try — doesn't modify commands, only presentation.
- **Setup:** `rtk init --global` registers auto-rewrite hook in Claude Code settings. Transparent to all conversations and subagents.
- **Repo:** github.com/rtk-ai/rtk

### Tier 1 — Domain-Relevant (Could Impact Current Work)

#### Kand (TA-Lib Replacement)
- **What:** Rust-based technical analysis library with Python/NumPy bindings. 50+ indicators, ~7ns ops, O(1) incremental updates.
- **Why it matters:** Directly relevant to feature computation (Stage 02) and live monitoring (Stage 07). Incremental update model is purpose-built for streaming bar data.
- **Adopt when:** Stage 07 live implementation, or if feature computation bottlenecks the 500-experiment autoresearch budget.
- **Caveat:** Check coverage of your specific indicators first. Custom features (regime-aware, cycle-level) won't be built-in. Adds Rust build dependency to pure-Python stack.
- **Repo:** github.com/kand-ta/kand

#### GitNexus (Code Intelligence)
- **What:** MCP server providing knowledge graph over codebase — impact analysis, change detection, process tracing.
- **Why it matters:** As archetypes multiply and shared utilities grow, "what breaks if I change this?" stops being trivial to answer manually.
- **Adopt when:** 3rd archetype added, ~15K+ LOC, or cross-stage refactoring feels risky.
- **Highest-value uses:** `impact` before touching shared code, `detect_changes` as pre-commit check, `processes` for experiment lifecycle tracing.
- **Already installed:** Yes (MCP server connected), just not indexed yet.

### Tier 2 — Useful at Scale (Dashboard / Growth Triggers)

#### SocratiCode (Semantic Code Search)
- **What:** MCP server with AST-aware vector + BM25 hybrid search. Auto file-watching, incremental indexing, 40M+ LOC capacity.
- **Why it matters:** "Where is X implemented?" at scale, polyglot search across Python + JS/TS when dashboard adds frontend.
- **Adopt when:** Dashboard milestone (polyglot codebase) or 50+ Python files.
- **vs GitNexus:** SocratiCode is search-first ("find the code"); GitNexus is relationship-first ("what connects to what"). Complementary, not competing.
- **Repo:** github.com/giancarloerra/SocratiCode

#### mcp2cli (API/MCP Unifier)
- **What:** Dynamically converts MCP servers, OpenAPI specs, and GraphQL endpoints into CLI tools. Token-efficient — keeps schemas server-side.
- **Why it matters:** Reduces token overhead when running multiple MCP servers simultaneously.
- **Adopt when:** Multiple MCP servers active (GitNexus + SocratiCode + custom), or dashboard exposes an API layer.
- **Repo:** github.com/knowsuchagency/mcp2cli

### Tier 3 — Niche / Low Priority

#### Cognee (Knowledge Retrieval)
- **What:** Knowledge graph + vector search hybrid for unstructured data. `add → cognify → search` API over Neo4j + vector DB.
- **Why it matters:** Could power a research journal system querying hundreds of experiment results across archetypes with natural language.
- **Adopt when:** Accumulated experiment history becomes too large for grep, or multi-agent knowledge sharing needed.
- **Not now because:** Pipeline data is structured (CSVs, JSON, typed params). Cognee solves unstructured retrieval. Neo4j + vector DB overhead isn't justified for current scale.
- **Repo:** github.com/topoteretes/cognee

#### CodeWiki (Auto Documentation)
- **What:** Multi-agent framework generating repo-level documentation with architecture diagrams, dependency graphs, cross-module analysis.
- **Why it matters:** Useful for onboarding collaborators or open-sourcing.
- **Not now because:** Your hand-maintained CONTEXT.md system carries more domain signal than auto-generated docs. At 38 Python files, generated docs would be thinner than what you have. Costs LLM tokens per run.
- **Adopt when:** Open-source / team handoff scenario.
- **Repo:** github.com/FSoft-AI4Code/CodeWiki

#### Ars Contexta (Context Management System)
- **What:** Claude Code plugin that auto-generates a full knowledge management system — 3-space architecture (self/notes/ops), 6-step processing pipeline, 4 automation hooks, 16+ slash commands.
- **Why it matters:** Research-backed (Zettelkasten, cognitive science). Solves session amnesia and knowledge persistence.
- **Skip because:** Your lightweight modular system already works and you built it from your own workflow. Ars Contexta targets users who *don't* have a working context system. Its 249 research claims and elaborate pipeline add complexity without clear ROI over your current approach.
- **Steal instead:** Session capture idea (auto-log what happened per Claude session) and periodic "reweave" reviews (do old SOPs still hold?).
- **Repo:** github.com/agenticnotetaking/arscontexta

---

## 3. Key Insight: Complementary, Not Competing

The modular .md system captures **how to work** (process knowledge, rules, SOPs).
Structural tooling captures **what connects to what** (code relationships, call graphs, blast radius).

They solve different problems:
- Solo operator with strong discipline? Modular .md system wins on simplicity.
- Multiple collaborators or high code interconnection? Automated indexing earns its keep.
- Both together? .md files steer the agent, knowledge graph prevents structural mistakes.

---

## 4. Open Questions for Future Sessions

- At what point does CLAUDE.md routing become its own maintenance burden? Is there a file count threshold?
- Could SOPs be auto-suggested (agent detects a repeated successful pattern and proposes codifying it)?
- How to handle SOP versioning — when a workflow evolves, update in place or archive old version?
- Would a lightweight "context manifest" per stage (machine-readable, not just CONTEXT.md) help with automated routing?
- GitNexus index maintenance overhead — does re-analyzing after every experiment cycle create friction in autoresearch loops?
- Kand indicator coverage — do built-in indicators cover rotational archetype needs, or are custom features dominant?

---

*This document is expected to grow. Add sections as new discussions happen.*
