# Kaithem is an interpreted project, I'm just using a makefile as a nice place to gather relevant commands.

# Needed to make CD work
.ONESHELL:


# We autoselect the user who will be running Kaithem if we install it.
ifdef KAITHEM_USER
KAITHEM_UID:=$(shell id -u $(KAITHEM_USER))
endif

ifdef KAITHEM_UID
KAITHEM_UID:=$(shell id -u $(KAITHEM_UID))
endif

ifndef KAITHEM_UID
KAITHEM_UID:=1000
endif

KAITHEM_USER:= $(shell id -un $(KAITHEM_UID))

# The dir the makefile is in
ROOT_DIR:=$(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))

export KAITHEM_UID
export KAITHEM_USER

ifndef KIOSK_HOME
KIOSK_HOME:="http://localhost:8002"
endif

USER:= $(shell id -un)


export USER
export KIOSK_HOME
export ROOT_DIR


include kaithem_scripts/Makefile
default: help 


.PHONY: help
help: # Show help for each of the available commands
	@cd ${ROOT_DIR}
	@echo
	@echo Kaithem Make CLI
	@echo "Quickstart: install-system-dependencies, .venv, install-dependencies, run, then visit localhost:8002"
	@echo "Most use the virtualenv in the project folder, unless you are already in a different venv"
	@echo "dev- commands always use the .venv in this project folder"
	@echo "root- commands require root and affect the whole system, and probably only work on Debian/PiOs/Ubuntu"
	@echo "user- commands affect your user"
	@echo
	@grep -E '^[a-zA-Z0-9\. -]+:.*#'  Makefile | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#'| fold -w 60 -s)\n\n"; done



.PHONY: update
update: # Fetch new code into this project folder
	git pull

.PHONY: dev-build-docs
dev-build-docs:
	@echo "Docs build removed, make important edits manually until we finish the Sphinx transition"


.PHONY: dev-count-lines
dev-count-lines: # Line count summary
	@uv tool run pygount --merge-embedded-languages --format=summary --names-to-skip="*.min.js,bip39.txt" --folders-to-skip="thirdparty,__pycache__,tests" kaithem/ scripts/

.PHONY: dev-count-test-lines
dev-count-test-lines: # Line count summary, counting the tests
	@uv tool run pygount --merge-embedded-languages --format=summary playwright/ kaithem/src/tests


.PHONY: dev-playwright-ui
dev-playwright-ui: # Open playwright tests UI
	@npx playwright test --ui


.PHONY: dev-record-playwright
dev-record-playwright: # Record playwright tests
	@npx playwright codegen http://localhost:8002


.PHONY: dev-update-playwright
dev-update-playwright: # Update playwright tests
	@npm install -D @playwright/test@latest
	@npx playwright install --with-deps

.PHONY: dev-file-lines
dev-file-lines: # Show files sorted by line count
	@uv tool run pygount --merge-embedded-languages --names-to-skip="*.min.js,bip39.txt" --folders-to-skip="thirdparty,__pycache__,tests" kaithem/ scripts/ | sort -nr -



.PHONY: dev-build
dev-build: dev-build-docs # Build for release
    # Workaround for this file being left behind and breaking
	@ ! rm .venv/lib/python3.12/site-packages/pandas/pyproject.toml
	@bash scripts/uv_pinned_build.sh


.PHONY: dev-publish-to-pypi
dev-publish-to-pypi: dev-build # Publish to PyPi. Do NOT directly build and publish without the frozen wheel script
	@~/.local/bin/uv publish

.PHONY: dev-import-16_9_buttons
dev-import-16_9_buttons: 
	@bash scripts/import_16x9_buttons.sh

.PHONY: dev-scalene-profile
dev-scalene-profile:
	@scalene --profile-all --use-virtual-time --cpu-sampling-rate=0.001 dev_run.py




.PHONY: dev-install-dev-tools
dev-install-dev-tools:
	@uv tool install licccheck
	@uv tool install pygount
	@uv tool install scalene

# Note that we use uv to test against different versions.  Eventually we will hopefully
# be able to go to all uv all the time.

# Due to the gstreamer hack we
.PHONY: dev-run-all-tests
dev-run-all-tests:
	@echo "Starting test server and running all playwright and pytest tests in active .venv"
	@echo "Stopping any other process named coverage"
	@killall -9 kmakefiletest
	@killall -9 coverage
	@sleep 1
	@coverage erase
	@coverage run testing_server.py --process-title kmakefiletest &
	@echo "Waiting for server to start"
	@sleep 5
	@wget --retry-connrefused --waitretry=1 --read-timeout=20 --quiet --timeout=15 -t 0 http://localhost:8002
	@npx playwright test --reporter=html  --workers 1 --max-failures 1
	@sleep 5
	@echo "Stopping server"
	@killall kmakefiletest
	@sleep 10
	@killall -9 kmakefiletest
	@coverage run --append -m pytest
	@coverage html -i
	@npx playwright show-report &
	@open htmlcov/index.html
	
	@echo "Rerunning pytest tests against 3.11, 3.12 and 3.13"

	@UV_PROJECT_ENVIRONMENT=.venv311  uv run --group dev --python 3.11 pytest
	@UV_PROJECT_ENVIRONMENT=.venv312  uv run --group dev --python 3.12 pytest
	@UV_PROJECT_ENVIRONMENT=.venv313  uv run --group dev --python 3.13 pytest


	@echo "Rerunning playwright tests in a clean venv without dev dependencies"

	@UV_PROJECT_ENVIRONMENT=.venv_clean_no_dev  uv run --no-dev testing_server.py --process-title kmakefiletest &
	@wget --retry-connrefused --waitretry=1 --read-timeout=20 --quiet --timeout=15 -t 0 http://localhost:8002
	@npx playwright test --reporter=html  --workers 1 --max-failures 1

	@echo "Finished running Kaithem test suite"