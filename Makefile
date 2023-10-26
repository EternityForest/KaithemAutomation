# Kaithem is an interpreted project, I'm just using a makefile as a nice place to gather relevant commands.

# Needed to make CD work
.ONESHELL:

ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))


default: help 

.PHONY: help install-dependencies clean-venv .venv run freeze-dependencies

help: # Show help for each of the Makefile recipes.
	@cd ${ROOT_DIR}
	@echo "This makefile does everything in .venv automatically for you."
	@grep -E '^[a-zA-Z0-9\. -]+:.*#'  Makefile | sort | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done


run: # Run the kaithem app.
	@cd ${ROOT_DIR}
	@.venv/bin/python -m kaithem

install-dependencies: # Install all dependendcies from the frozen requirements into the venv
	@cd ${ROOT_DIR}
	@.venv/bin/python -m pip install --ignore-installed -r requirements_frozen.txt

update-dependencies: # Install latest version of dependencies into the venv. New versions might break something!
	@cd ${ROOT_DIR}
	@.venv/bin/python -m pip install --ignore-installed  -U -r direct-dependencies.txt


clean-venv: # Install all dependendcies from the frozen requirements into the venv
	@cd ${ROOT_DIR}
	@.venv/bin/python -m pip uninstall -y -r <(pip freeze -l)

.venv: # Create the virtualenv .in .the kaithem root dir. venv
	@cd ${ROOT_DIR}
	@virtualenv .venv

freeze-dependencies: # Create requirements_frozen.txt
	@cd ${ROOT_DIR}
	@.venv/bin/python -m pip freeze -l > requirements_frozen.txt
	# If kaithem itself installed here, avoid circular nonsense
	sed -i '/kaithem=.*/d' ./requirements_frozen.txt

