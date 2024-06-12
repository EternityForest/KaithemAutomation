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

# todo Escape undercores in md files, handsdown doesn't escape them ye
.PHONY: dev-build-docs
dev-build-docs:
	@handsdown -i kaithem/api/ -o kaithem/src/docs/api


.PHONY: dev-count-lines
dev-count-lines: # Line count summary
	@poetry run pygount --merge-embedded-languages --format=summary --names-to-skip="*.min.js,bip39.txt" --folders-to-skip="thirdparty,__pycache__,tests" kaithem/ scripts/

.PHONY: dev-count-test-lines
dev-count-test-lines: # Line count summary, counting the tests
	@poetry run pygount --merge-embedded-languages --format=summary playwright/ kaithem/src/tests


.PHONY: dev-playwright-ui
dev-playwright-ui: # Open playwright tests UI
	@npx playwright test --ui


.PHONY: dev-record-playwright
dev-record-playwright: # Record playwright tests
	@npx playwright codegen http://localhost:8002

.PHONY: dev-file-lines
dev-file-lines: # Show files sorted by line count
	@poetry run pygount --merge-embedded-languages --names-to-skip="*.min.js,bip39.txt" --folders-to-skip="thirdparty,__pycache__,tests" kaithem/ scripts/ | sort -nr -



.PHONY: dev-build
dev-build: dev-build-docs # Build for release
	@poetry build
	@poetry freeze-wheel

