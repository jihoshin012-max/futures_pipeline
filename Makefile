# pipeline/Makefile — Pipeline automation targets
SHELL := /bin/bash
PYTHON := python

.PHONY: help check-p2 validate zone-prep archive-sweep

help:
	@echo "Pipeline targets:"
	@echo "  help           — Show this help"
	@echo "  check-p2       — Verify P2 holdout flag status"
	@echo "  validate       — Run data validation (stage 01)"
	@echo "  zone-prep      — Run zone data preparation"
	@echo "  archive-sweep  — Archive a completed sweep (NAME=<dir>)"

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

archive-sweep:
	@test -n "$(NAME)" || { echo "Usage: make archive-sweep NAME=<sweep_dir>"; exit 1; }
	@test -d "stages/04-backtest/rotational/$(NAME)" || { echo "ERROR: stages/04-backtest/rotational/$(NAME) not found"; exit 1; }
	mkdir -p archive/sweeps/$(NAME)
	mv stages/04-backtest/rotational/$(NAME)/* archive/sweeps/$(NAME)/
	rmdir stages/04-backtest/rotational/$(NAME)
	@echo "Archived $(NAME) to archive/sweeps/$(NAME)/"
