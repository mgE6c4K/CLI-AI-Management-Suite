PREFIX ?= $(HOME)/.local
BIN := $(PREFIX)/bin
PYTHON ?= python3

install: claude-backup
	install -d "$(BIN)"
	printf '#!/bin/sh\nexec $(PYTHON) "%s/om.py" "$$@"\n' "$(CURDIR)" > "$(BIN)/om"
	chmod 755 "$(BIN)/om"
	@echo "installed $(BIN)/om"
	@echo 'for nvim (codecompanion), add to your shell rc:  eval "$$(om env)"'

claude-backup:
	@if [ -f claude-backup/Makefile ]; then $(MAKE) -C claude-backup; \
	else echo "claude-backup add-on not checked out (git submodule update --init); om runs without it"; fi

uninstall:
	rm -f "$(BIN)/om"

test:
	$(PYTHON) -B test_om.py

.PHONY: install claude-backup uninstall test
