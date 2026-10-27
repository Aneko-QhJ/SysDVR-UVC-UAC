PYTHON ?= $(shell command -v python3.13 2>/dev/null || command -v python3.12 2>/dev/null || command -v python3)

.PHONY: help check check-all check-file quick index links

help:
	@echo "make check       - current-topic tests (fast, default)"
	@echo "make check-all   - all 180+ offline test files"
	@echo "make check-file  - all tests, one process per file"
	@echo "make index       - regenerate docs/INDEX.md and tools/INDEX.md"
	@echo "make links       - check relative links in public docs"

check: quick

quick:
	$(PYTHON) tests/run_all.py --quick

check-all:
	$(PYTHON) tests/run_all.py

check-file:
	$(PYTHON) tests/run_all.py --per-file

index:
	$(PYTHON) tools/index_docs.py
	$(PYTHON) tools/index_tools.py

links:
	$(PYTHON) tools/check_links.py
