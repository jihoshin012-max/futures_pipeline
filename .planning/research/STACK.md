# Stack Research

**Domain:** Futures trading strategy research and deployment pipeline (NQ, signal-touch archetype)
**Researched:** 2026-03-13
**Confidence:** MEDIUM — Core Python data science stack is HIGH confidence; specialized trading libraries verified via PyPI/docs; ACSIL generation pattern is custom (no prior art, so assessed from first principles)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12.x | Primary runtime | 3.12 is the current stable LTS with best perf improvements (per-interpreter GIL, faster bytecode). Avoid 3.13+ until free-threading stabilizes with scientific stack. |
| pandas | 2.2.x | OHLCV data manipulation, time-series indexing, IS/OOS slicing | 2.2.x is the last stable 2.x series — compatible with NumPy 2.x; broadly tested in quant workflows. pandas 3.0 (Jan 2026) is too new; avoid until ecosystem catches up. |
| NumPy | 2.1.x | Array math, vectorized indicator computation, feature arrays | NumPy 2.x released stable Dec 2025. Use 2.1.x (not 2.4 yet) for compatibility with hmmlearn and other C-extension libraries. |
| SciPy | 1.14.x | Statistical tests: t-tests, Wilcoxon, permutation tests, Bonferroni | Industry standard for stats in Python. `scipy.stats.permutation_test` and `statsmodels.stats.multitest.multipletests` are the two-library pattern used for trading statistical validation. |
| statsmodels | 0.14.x | Multiple comparison correction (`multipletests`), OLS sanity checks | Provides `bonferroni`, `holm`, `fdr_bh` methods in one call. Used for Bonferroni-adjusted p-value gates across the hypothesis iteration budget. |
| hmmlearn | 0.3.3 | HMM regime fitter (`GaussianHMM`) producing regime_labels.csv | Only maintained HMM library with scikit-learn-compatible API. Under limited-maintenance mode — pin to 0.3.3. No replacement exists for GaussianHMM in this role. |
| scikit-learn | 1.5.x | Feature scaling (StandardScaler), cross-validation utilities, binning (KBinsDiscretizer for BinnedScoringAdapter) | Industry standard. BinnedScoringAdapter bin_edges can be computed via `numpy.percentile` or `sklearn.preprocessing.KBinsDiscretizer`. Use sklearn for the latter when quantile boundaries are needed. |
| Git + bash | system | Autocommit loop, pre/post-commit hooks, holdout guard, audit enforcement | The Karpathy autoresearch pattern is built on git: agent edits file → harness evaluates → keep/revert via `git checkout` or `git commit`. Shell hooks enforce structural pipeline rules. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyarrow | 17.x | Parquet read/write for OHLCV bar data and feature DataFrames | Use parquet (not CSV) for all persisted data. Parquet is ~10x faster to read than CSV and handles typed columns correctly. Required by pandas `.to_parquet()`. |
| joblib | 1.4.x | Parallelizing overnight autoresearch loops across parameter sweeps | Use when Stage 02/03/04 drivers need to evaluate multiple feature/hypothesis variants in parallel. Pairs naturally with scikit-learn pipelines. |
| quantstats | 0.0.64 | HTML tearsheet generation: Sharpe, drawdown, win rate, monthly returns | Use for Stage 05 statistical assessment output. Generates self-contained HTML report from a returns series. Do not build custom tearsheet infrastructure — this covers 95% of reporting needs. |
| jsonschema | 4.23.x | Validating `config_schema.json` entries at engine load time | Structural enforcement of backtest config: prevents silent misconfiguration. Required for the determinism guarantee. |
| pytest | 8.x | Unit tests for engine components, statistical gate functions, data loaders | Use pytest, not unittest. Fixtures and parametrize markers make IS/OOS split testing clean. |
| black | 24.x | Code formatting | Enforced in pre-commit hook. Zero-config. Avoids style debates in autoresearch loop output. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| VS Code + Python extension | Primary editor | Not required by pipeline, but C++ ACSIL requires a separate build environment (see ACSIL section below). |
| Visual C++ Build Tools (Windows) | Compiling ACSIL `.dll` from generated `.cpp` | Sierra Chart ACSIL is Windows-only C++. `Build >> Build With Visual C++ - Debug` inside Sierra Chart. The Python pipeline generates the `.cpp` source; human or CI compiles and links the DLL. |
| pre-commit (framework) | Managing git hook scripts declaratively | Use native git hooks (`.git/hooks/pre-commit`, `post-commit`) rather than the `pre-commit` pip package — the project's hooks contain domain-specific logic (holdout guard, audit append, period rollover warning) that cannot be expressed as generic hooks. |
| jsonschema CLI | Validating config files offline | `python -m jsonschema` for spot-checking config before runs. |

---

## ACSIL Code Generation Pattern

Sierra Chart's ACSIL is a C++ framework with no Python bindings and no external code-generation tooling. The pipeline generates C++ source text as a string from Python, then writes it to a `.cpp` file. This is a **text generation problem, not an API integration problem**.

**Recommended approach:** Pure Python string generation using f-strings or Jinja2 templates.

| Approach | Recommendation | Rationale |
|----------|---------------|-----------|
| f-strings (simple studies) | Use for simple linear studies (< 150 lines of C++) | Zero dependencies, readable, easy to diff |
| Jinja2 (2.x / 3.x) | Use for multi-leg exit logic, conditional blocks, routing waterfall | Jinja2 templates separate structure from values; easier to maintain as the archetype evolves |
| LLVM / clang-format | Optional: format generated C++ | Use `clang-format` if Sierra Chart's compiler produces confusing error messages |

The generated `.cpp` must conform to ACSIL's `SCSFExport` function signature and Sierra Chart's `sc.StudyControl`, `sc.Input`, `sc.Subgraph` conventions. All ACSIL-specific constants and enums come from the Sierra Chart include files — the pipeline should store canonical ACSIL snippets in a `templates/acsil/` directory to prevent hallucinated API usage.

---

## Autoresearch Loop Infrastructure

The Karpathy autoresearch pattern (released March 2026, 30K+ stars in one week) drives overnight experiment runs. For this pipeline, the pattern maps as:

| Pattern Element | Pipeline Implementation |
|----------------|------------------------|
| Agent edits one file | Claude (or human) edits `program.md` to steer; agent edits feature/hypothesis file |
| Fixed harness evaluates | Stage 04 driver / Stage 02 driver / Stage 03 driver (immutable harness) |
| Measure improvement | Statistical gate: adjusted p-value, drawdown gate, Sharpe threshold |
| Keep or revert | `git commit` (keep) or `git checkout HEAD -- <file>` (revert) |
| Repeat overnight | Driver loop with iteration budget from `pipeline_rules` config |

**No additional ML experiment tracking library is needed.** The audit_log.md + git commit log provide full lineage. MLflow/W&B add overhead without benefit when the evaluation harness is already the source of truth. Do not add them.

---

## Installation

```bash
# Create environment
python -m venv .venv
source .venv/Scripts/activate  # Windows

# Core science stack
pip install "pandas==2.2.*" "numpy==2.1.*" "scipy==1.14.*" "statsmodels==0.14.*"

# ML / regime
pip install "scikit-learn==1.5.*" "hmmlearn==0.3.3"

# Data persistence
pip install "pyarrow==17.*"

# Performance reporting
pip install "quantstats==0.0.64"

# Config validation
pip install "jsonschema==4.23.*"

# Template generation (for ACSIL, optional)
pip install "jinja2==3.*"

# Parallelism
pip install "joblib==1.4.*"

# Dev / test
pip install "pytest==8.*" "black==24.*"
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Custom backtest engine (dynamic dispatch) | vectorbt | vectorbt for parameter sweeps across thousands of configurations simultaneously; custom engine when you need exact multi-leg partial exit simulation with per-bar state |
| Custom backtest engine | backtrader | backtrader for live paper trading integration; not recommended here — unmaintained since 2021, complex for custom archetypes |
| Custom backtest engine | backtesting.py | backtesting.py for simple signal-in, signal-out strategies without multi-leg exits; too limited for BinnedScoringAdapter + trail steps |
| pandas 2.2.x | pandas 3.0.x | pandas 3.0 when ecosystem (hmmlearn, quantstats) has verified compatibility — not yet in March 2026 |
| hmmlearn | pomegranate | pomegranate if GPU acceleration of HMM needed; heavier dependency, less stable API |
| Native git hooks | pre-commit framework | pre-commit framework if hooks are generic (linting, formatting only); not appropriate here because holdout guard logic is domain-specific |
| Jinja2 for ACSIL | Mako / string.Template | Any of these work; Jinja2 has the largest ecosystem and best IDE support |
| statsmodels multipletests | pingouin | pingouin for interactive statistical exploration in notebooks; statsmodels for programmatic pipeline use |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Zipline / Zipline-Reloaded | Event-driven per-bar Python execution; backtests on minute NQ data are 10-100x slower than needed; unmaintained Quantopian codebase | Custom engine with NumPy vectorized bar loops |
| QuantLib (Python bindings) | Designed for derivatives pricing, not discretionary entry/exit simulation; steep API learning curve with no benefit for NQ futures | scipy.stats + statsmodels for statistical needs |
| backtrader | Unmaintained since 2021; complex Cerebro architecture fights against dynamic dispatch pattern; no active community | Custom engine |
| MLflow / W&B / Optuna | Experiment tracking overhead unjustified when audit_log.md + git IS the experiment record; Optuna hyperparameter search is antithetical to Karpathy pattern (agent proposes, fixed harness evaluates) | Git commit log + audit_log.md |
| polars | Fast for large-scale analytics but breaks statsmodels/hmmlearn integration; pandas is the lingua franca of the statistical stack | pandas 2.2.x (use pyarrow backend for speed when needed) |
| pandas 3.0.x | Too new (Jan 2026); hmmlearn, quantstats not yet verified compatible; new string dtype changes silent behavior | pandas 2.2.x |
| NumPy 2.4.x | Latest but risky — C-extension libraries (hmmlearn) may have ABI issues | NumPy 2.1.x |
| Celery / Ray | Distributed task queue overkill for single-machine overnight loop; adds operational complexity | joblib for local parallelism |
| SQLite / PostgreSQL | Relational DB adds schema migration overhead for append-only time-series data | Parquet files via pyarrow |

---

## Stack Patterns by Variant

**For overnight autoresearch loop (Stage 02/03/04 drivers):**
- Use `joblib.Parallel` with `n_jobs=-1` to parallelize candidate evaluation
- Each worker runs the custom backtest engine on its parameter set, returns a metrics dict
- Main loop collects results, applies `statsmodels.stats.multitest.multipletests` with `bonferroni` method
- Keep/revert decision via `subprocess.run(['git', 'checkout', 'HEAD', '--', filepath])` on revert

**For HMM regime fitter (hmm_regime_fitter.py):**
- `hmmlearn.hmm.GaussianHMM(n_components=3, covariance_type='full', n_iter=100)`
- Features: log returns, rolling 20-bar volatility, bar range normalized by ATR
- Serialize model with `joblib.dump` (not pickle — joblib handles numpy arrays correctly)
- Output: `regime_labels.csv` with DatetimeIndex + integer regime column

**For BinnedScoringAdapter:**
- Compute `bin_edges` on P1a (calibrate split) using `numpy.percentile` at chosen quantile boundaries
- Freeze `bin_edges` as JSON in scoring model config — never recompute on P2
- At inference: `numpy.digitize(score, bin_edges)` for bin assignment

**For ACSIL code generation (Stage 06):**
- Input: validated strategy config JSON + archetype template
- Output: `.cpp` file with `SCSFExport` function implementing multi-leg exit logic
- Human compiles via Sierra Chart's Build menu; compiled `.dll` deployed to Sierra Chart

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| pandas==2.2.x | numpy==2.1.x | 2.2.2 was first pandas version verified with NumPy 2.x |
| hmmlearn==0.3.3 | numpy==2.1.x, scikit-learn==1.5.x | Pin hard; limited-maintenance, no new releases expected |
| quantstats==0.0.64 | pandas==2.2.x | Verify on install; quantstats has had pandas 2.x compatibility patches |
| statsmodels==0.14.x | pandas==2.2.x, scipy==1.14.x | statsmodels 0.14 explicitly supports pandas 2.x |
| pyarrow==17.x | pandas==2.2.x | pyarrow is pandas' recommended Parquet backend; version should match pandas major |
| scikit-learn==1.5.x | numpy==2.1.x | sklearn 1.5 added full NumPy 2.x support |

---

## Sources

- [karpathy/autoresearch GitHub](https://github.com/karpathy/autoresearch) — Pattern verified as released March 6, 2026; 630-line single-file Python; keep/revert loop confirmed
- [pandas 3.0 release notes](https://pandas.pydata.org/docs/dev/whatsnew/v3.0.0.html) — Verified pandas 3.0 released January 21, 2026; string dtype changes documented
- [hmmlearn PyPI](https://pypi.org/project/hmmlearn/) — Version 0.3.3 confirmed current; limited-maintenance status confirmed
- [statsmodels multipletests docs](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html) — Bonferroni, holm, fdr_bh methods verified in 0.14.x
- [SciPy permutation_test docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html) — Verified in SciPy 1.17.x
- [Sierra Chart ACSIL docs](https://www.sierrachart.com/index.php?page=doc/AdvancedCustomStudyInterfaceAndLanguage.php) — C++ only, no Python bindings; Build with Visual C++ confirmed
- [NumPy releases](https://github.com/numpy/numpy/releases) — NumPy 2.4.0 released December 2025 (latest); 2.1.x recommended for compatibility
- [QuantStart HMM regime detection](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/) — hmmlearn GaussianHMM pattern for regime labeling confirmed (MEDIUM confidence)
- [Efficient data storage for time series](https://medium.com/@kyle-t-jones/efficient-data-storage-strategies-for-time-series-feather-orc-and-parquet-4c97ec85bb05) — Parquet preferred over Feather for persistent storage; pyarrow backend (MEDIUM confidence)
- [Ultimate Python Quant Trading Ecosystem 2025](https://medium.com/@mahmoud.abdou2002/the-ultimate-python-quantitative-trading-ecosystem-2025-guide-074c480bce2e) — Ecosystem survey confirming standard stack (LOW confidence — single community source)

---

*Stack research for: Futures trading strategy research and deployment pipeline (NQ, signal-touch)*
*Researched: 2026-03-13*
