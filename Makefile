# Kaithem is an interpreted project, I'm just using a makefile as a nice place to gather relevant commands.

# Needed to make CD work
.ONESHELL:

.DELETE_ON_ERROR:

COMPOSE_FILE := docker/docker-compose.yaml
IN_DEV_DOCKER := docker compose -f $(COMPOSE_FILE) up -d kaithem-dev && docker compose -f $(COMPOSE_FILE) exec kaithem-dev
IN_APP_DOCKER := docker compose -f $(COMPOSE_FILE) up -d kaithem && docker compose -f $(COMPOSE_FILE) exec kaithem
PLAYWRIGHT := docker compose -f $(COMPOSE_FILE) run --rm playwright npx playwright
# We autoselect the user who will be running Kaithem if we install it.
ifdef KAITHEM_USER
KAITHEM_UID:=$(shell id -u $(KAITHEM_USER))
endif

ifdef KAITHEM_UID
KAITHEM_UID:=$(shell id -u $(KAITHEM_UID))
endif

ifndef KAITHEM_UID
KAITHEM_UID:=$(shell id -u)
endif

ifndef KAITHEM_GROUP
KAITHEM_GROUP:=$(shell id -g)
endif

KAITHEM_USER:= $(shell id -un $(KAITHEM_UID))

# The dir the makefile is in
ROOT_DIR:=$(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))

export KAITHEM_UID
export KAITHEM_USER
export KAITHEM_GROUP

ifndef KIOSK_HOME
KIOSK_HOME:="http://localhost:8002"
endif

USER:= $(shell id -un)
KAITHEM_VERSION:=$(shell python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')

export USER
export KIOSK_HOME
export ROOT_DIR
export KAITHEM_VERSION

default: help 


.PHONY: help
help: # Show help for each of the available commands
	@cd ${ROOT_DIR}
	@echo
	@echo Kaithem Make CLI.  
	@echo "Quickstart: Get rust and wasm target, get node, install uv, then run 'make dev-build' to build the project and 'make dev-run-sandbox' to run it."
	@echo "Most use the virtualenv in the project folder, unless you are already in a different venv"
	@echo "dev- commands always use the .venv in this project folder"
	@echo "root- commands require root and affect the whole system, and probably only work on Debian/PiOs/Ubuntu"
	@echo "user- commands affect your user"
	@echo
	@grep -E '^[a-zA-Z0-9\. -]+:.*#'  Makefile | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#'| fold -w 60 -s)\n\n"; done



.PHONY: update
update: # Fetch new code into this project folder
	git pull

.PHONY: dev-install-system-dependencies
dev-install-system-dependencies: # Install system dependencies for Kaithem development
	@bash kaithem/data/debian_setup_dependencies.sh
	@bash kaithem/data/debian_runtime_dependencies.sh

.PHONY: dev-build-docs
dev-build-docs:
	@uv run sphinx-build -M markdown doc_source doc_build_md
	@rm -rf kaithem/src/docs/api
	@cp -r doc_build_md/markdown/autoapi/kaithem/api/ kaithem/src/docs/
	@rm -rf doc_build_md


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
	@${PLAYWRIGHT} codegen http://localhost:8002


.PHONY: dev-file-lines
dev-file-lines: # Show files sorted by line count
	@uv tool run pygount --merge-embedded-languages --names-to-skip="*.min.js,bip39.txt" --folders-to-skip="thirdparty,__pycache__,tests" kaithem/ scripts/ | sort -nr -

.PHONY: dev-build-vite
dev-build-vite:
	@npm run build

.PHONY: dev-watch-vite
dev-watch-vite:
	@npx vite build --watch


.PHONY: dev-build
dev-build: dev-build-docs  dev-build-builtin-kegs dev-build-vite # Build for release
    # Workaround for this file being left behind and breaking
	@ ! rm .venv/lib/python3.12/site-packages/pandas/pyproject.toml
	@bash scripts/uv_pinned_build.sh

.PHONY: dev-run-sandbox
dev-run: # Run kaithem with throwaway user data folder 
	@uv run python3 testing_server.py

.PHONY: dev-publish-to-pypi
dev-publish-to-pypi: dev-build # Publish to PyPi. Do NOT directly build and publish without the frozen wheel script
	@twine upload dist/*

.PHONY: dev-import-16_9_buttons
dev-import-16_9_buttons: 
	@bash scripts/import_16x9_buttons.sh

.PHONY: dev-scalene-profile
dev-scalene-profile:
	@scalene --profile-all --use-virtual-time --cpu-sampling-rate=0.001 dev_run.py


.PHONY: dev-build-builtin-kegs
dev-build-builtin-kegs:
	@bash scripts/build-builtin-kegs.sh


.PHONY: dev-install-dev-tools
dev-install-dev-tools:
	@uv tool install licccheck
	@uv tool install pygount
	@uv tool install scalene
# 	@uv tool install sphinx --with sphinx-autoapi --with sphinx-markdown-builder --with sphinx-pyproject

# Note that we use uv to test against different versions.  Eventually we will hopefully
# be able to go to all uv all the time.

# Due to the gstreamer hack we
.PHONY: dev-run-all-tests
dev-run-all-tests:
	@trap 'echo "Stopping all subprocesses..."; kill -9 0' EXIT INT TERM
	@echo "Starting test server and running all playwright and pytest tests in active .venv"
	@echo "Stopping any other process named coverage"
	@killall -9 kmakefiletest
	@killall -9 coverage
	@sleep 1
	@ ${IN_DEV_DOCKER} coverage erase
	@ ${IN_DEV_DOCKER} pw-jack uv run coverage run testing_server.py --process-title kmakefiletest > /dev/shm/kmakefiletest.log &
	@echo "Waiting for server to start"
	@sleep 5
	@echo "wgetting server to make sure it is up, this may take a minute"
	@wget --retry-connrefused --waitretry=1 --read-timeout=20 --quiet --timeout=15 -t 0 http://localhost:8002
	@echo "Running playwright tests"
	@${PLAYWRIGHT} test --reporter=html  --workers 1 --max-failures 1
	@sleep 5
	@echo "Stopping server"
	@killall kmakefiletest
	@sleep 1
	@killall -w kmakefiletest
	@sleep 10
	@${IN_DEV_DOCKER} coverage run --append -m pytest
	@${IN_DEV_DOCKER} coverage html -i
	@open htmlcov/index.html
	@open playwright-report/index.html

	@echo "Rerunning pytest tests against 3.11, 3.12 and 3.13 on local machine"

	@UV_PROJECT_ENVIRONMENT=.test_venvs/.venv311  pw-jack  uv run --group dev --python 3.11 pytest
	@UV_PROJECT_ENVIRONMENT=.test_venvs/.venv312  pw-jack  uv run --group dev --python 3.12 pytest
	@UV_PROJECT_ENVIRONMENT=.test_venvs/.venv313  pw-jack uv run --group dev --python 3.13 pytest


	@echo "Rerunning playwright tests in a clean venv without dev dependencies"

	@UV_PROJECT_ENVIRONMENT=.test_venvs/.venv_clean_no_dev  pw-jack  uv run --python=/usr/bin/python3 --no-dev testing_server.py --process-title kmakefiletest  &
	@wget --retry-connrefused --waitretry=1 --read-timeout=20 --quiet --timeout=15 -t 0 http://localhost:8002
	@${PLAYWRIGHT} test --reporter=html  --workers 1 --max-failures 1

	@echo "Finished running Kaithem test suite"
	@echo "Stopping server"
	@killall kmakefiletest
	@sleep 10
	@killall -9 kmakefiletest


.PHONY: dev-build-docker
dev-build-docker:
	@echo "Building docker images for Kaithem ${KAITHEM_VERSION}"
	@echo "Dev user must be 1000, current is: ${KAITHEM_USER}  UID: ${KAITHEM_UID}  GID: ${KAITHEM_GROUP}"
	@cd ./docker
# 	@docker compose build --progress=plain kaithem-builder
	@docker compose build --progress=plain kaithem-dev
# 	@docker compose build --progress=plain kaithem-kiosk
# 	@docker compose build --progress=plain playwright
	@docker compose build --progress=plain kaithem



.PHONY: dev-docker-shell
dev-docker-shell:
	@${IN_DEV_DOCKER} /bin/bash



.PHONY: dev-docker-kiosk
dev-docker-kiosk: # Launch the kiosk browser in a docker.
	@cd ./docker
	@KIOSK_URL=http://localhost:8002 docker compose run --remove-orphans kaithem-kiosk 


.PHONY: dev-docker-clean-storage
dev-docker-clean-storage:
	@cd ./docker
	@docker compose rm -v
