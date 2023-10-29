# Kaithem is an interpreted project, I'm just using a makefile as a nice place to gather relevant commands.

# Needed to make CD work
.ONESHELL:

ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
INTERPRETER:=$(shell bash scripts/makefile_choose_interpreter.sh)


default: help 

.PHONY: help install-dependencies clean-venv .venv run freeze-dependencies

help: # Show help for each of the available commands
	@cd ${ROOT_DIR}
	@echo
	@echo Kaithem Make CLI
	@echo "Quickstart: install-system-dependencies, .venv, install-dependencies, run, then visit localhost:8002"
	@echo "Most use the virtualenv in the project folder, unless you are already in a different venv"
	@echo "dev- commands always use the venv in the project folder"
	@echo
	@grep -E '^[a-zA-Z0-9\. -]+:.*#'  Makefile | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done
	@echo

run: # Run the kaithem app.
	@cd ${ROOT_DIR}
	@${INTERPRETER} -m kaithem	

install-system-dependencies: # Install non-python features that need apt
	@sudo apt install python3-virtualenv scrot mpv lm-sensors  python3-netifaces python3-gst-1.0  gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad  swh-plugins  tap-plugins  caps   gstreamer1.0-plugins-ugly fluidsynth libfluidsynth3 gstreamer1.0-pocketsphinx x42-plugins baresip gstreamer1.0-opencv  gstreamer1.0-vaapi python3-opencv


install: # Install all dependendcies from the frozen requirements into the venv
	@cd ${ROOT_DIR}
	@${INTERPRETER} -m pip install --ignore-installed -r requirements_frozen.txt
	@pip install --editable .

.venv: # Create the virtualenv in the project folder
	@cd ${ROOT_DIR}
	@virtualenv .venv

dev-update-dependencies: # Install latest version of dependencies into the venv. New versions might break something!
	@cd ${ROOT_DIR}
	@.venv/bin/python -m pip install --ignore-installed  -U -r direct-dependencies.txt

dev-clean-venv: # Cleans the .venv in the project folder
	@cd ${ROOT_DIR}
	@.venv/bin/python -m pip uninstall -y -r <(pip freeze -l)


dev-freeze-dependencies: # Create requirements_frozen.txt
	@cd ${ROOT_DIR}
	@.venv/bin/python -m pip freeze -l > requirements_frozen.txt
	# If kaithem itself installed here, avoid circular nonsense
	@sed -i '/.*kaithem.*/d' ./requirements_frozen.txt

