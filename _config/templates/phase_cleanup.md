# Phase Cleanup: {PHASE_NAME}

Date: {DATE}
Archetype: {ARCHETYPE}

---

## 1. Reconciliation

Run `make reconcile` (or `make reconcile DETAIL=1` for per-file listing).

```
{PASTE RECONCILE OUTPUT HERE}
```

Status: {CLEAN / NEEDS CLEANUP}

If NEEDS CLEANUP, list issues and resolution:
- {issue}: {resolution}

## 2. File Inventory

List all files produced by this analysis phase.

| File | Location | Type | Notes |
|------|----------|------|-------|
| {filename} | {path} | script / report / data / prompt | {row count, etc.} |

Files NOT listed in the prompt but produced (flag for inclusion or exclusion):
- {extra file}: {include in commit N / exclude (reason)}

## 3. Pre-Existing Unstaged Work

Files modified or untracked from PRIOR phases (commit BEFORE this phase):

| File | Origin | Action |
|------|--------|--------|
| {file} | {prior phase} | Commit as {commit 0x} / Skip (reason) |

## 4. Path Corrections

Paths assumed by the prompt vs actual pipeline layout:

| Prompt assumed | Actual location | Action |
|---------------|-----------------|--------|
| {assumed path} | {actual path} | Use actual / Create directory / Move file |

## 5. Commit Sequence

### Commit 0 (pre-existing work, if any):
- Files: {list}
- Message: `"{message}"`

### Commit 1 — {description}:
- Files: {list}
- Message: `"{message}"`

### Commit 2 — {description}:
- Files: {list}
- Message: `"{message}"`

{Add more commits as needed}

### Commit N — Documentation updates:
- Files: audit trail, changelog, session transfer
- Message: `"{message}"`

## 6. Documentation Updates

### Audit Trail
Location: `shared/archetypes/{archetype}/docs/NQ_Zone_Audit_Trail.md`

```
{AUDIT ENTRY TEXT — append, do not overwrite}
```

### Changelog
Location: `shared/archetypes/{archetype}/acsil/CHANGELOG.md`

```
{CHANGELOG ENTRY TEXT — prepend to newest-first list}
```

### Session Transfer
Location: `shared/archetypes/{archetype}/docs/SESSION_TRANSFER.md`

Updates:
- Immediate next steps: {update}
- Key results: {add section}
- Queued work: {add items}

## 7. Verification

After all commits:

- [ ] `git log --oneline -{N}` shows correct commit sequence
- [ ] `git status` shows clean tree (only .reconcile_ignore exceptions)
- [ ] `make reconcile` returns CLEAN
- [ ] Audit trail entry present
- [ ] Changelog entry present
- [ ] Session transfer updated

## 8. Notes

{Any deviations from the prompt, pre-commit hook warnings, etc.}
