# pipeline/Makefile — Pipeline automation targets
SHELL := /bin/bash
PYTHON := python

.PHONY: help check-p2 validate zone-prep replication-gate archive-sweep verify-data reconcile

help:
	@echo "Pipeline targets:"
	@echo "  help           — Show this help"
	@echo "  check-p2       — Verify P2 holdout flag status"
	@echo "  validate       — Run data validation (stage 01)"
	@echo "  zone-prep      — Run zone data preparation"
	@echo "  replication-gate — Run zone touch replication gate (79/79)"
	@echo "  archive-sweep  — Archive a completed sweep (NAME=<dir>)"
	@echo "  verify-data    — Verify source data integrity (SHA256)"
	@echo "  reconcile      — Pre-cleanup reconciliation (untracked, modified, paths)"

check-p2:
	@if [ -f stages/04-backtest/p2_holdout/holdout_locked_P2.flag ]; then \
		echo "P2 LOCKED — holdout flag present"; \
	else \
		echo "WARNING: P2 NOT LOCKED — holdout flag missing"; \
	fi

validate:
	$(PYTHON) stages/01-data/validate.py

zone-prep:
	$(PYTHON) stages/01-data/scripts/run_zone_prep.py

replication-gate:
	@echo "Running zone touch replication gate..."
	$(PYTHON) stages/04-backtest/zone_touch/replication_harness.py

verify-data:
	$(PYTHON) scripts/verify_data_integrity.py

archive-sweep:
	@test -n "$(NAME)" || { echo "Usage: make archive-sweep NAME=<sweep_dir>"; exit 1; }
	$(PYTHON) stages/04-backtest/scripts/archive_sweep.py $(NAME)

reconcile:
	@$(PYTHON) scripts/reconcile.py $(if $(DETAIL),--detail,)
