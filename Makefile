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

ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
INTERPRETER:=$(shell bash scripts/makefile_choose_interpreter.sh)

export KAITHEM_UID
export KAITHEM_USER

ifndef KIOSK_HOME
KIOSK_HOME:="http://localhost:8002"
endif

export KIOSK_HOME


default: help 

.PHONY: help install-dependencies clean-venv .venv run freeze-dependencies

help: # Show help for each of the available commands
	@cd ${ROOT_DIR}
	@echo
	@echo Kaithem Make CLI
	@echo "Quickstart: install-system-dependencies, .venv, install-dependencies, run, then visit localhost:8002"
	@echo "Most use the virtualenv in the project folder, unless you are already in a different venv"
	@echo "dev- commands always use the .venv in this project folder"
	@echo "root- commands require root and affect the whole system, and probably only work on Debian/PiOs/Ubuntu"
	@echo
	@grep -E '^[a-zA-Z0-9\. -]+:.*#'  Makefile | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#'| fold -w 60 -s)\n\n"; done
	@echo
	@echo "To install Kaithem as a specific user, use make KAITHEM_USER=name <command>"
	@echo  "The default selected user will be uid1000, which will normally be the user account"
	@echo "On a single-user system"
	@echo "Use CONFIRM=1 to bypass prompts for scripted install"
	@echo
	@echo "Selected user for install is $(KAITHEM_UID)/$(KAITHEM_USER)"






${ROOT_DIR}/.venv: # Create the virtualenv in the project folder
	@cd ${ROOT_DIR}
	@virtualenv .venv

restart-pipewire:
	@echo "Tries to restart everything, including some that may fail because they're not installed"
	@systemctl --user restart pipewire pipewire-pulse wireplumber pipewire-media-session


dev-make-venv: ${ROOT_DIR}/.venv # Make the virtualenv in this project folder.
	@echo "Making venv if not present"

dev-install: dev-make-venv # Install Kaithem and all it's dependencies in the Venv.
	@cd ${ROOT_DIR}
	@.venv/bin/python -m pip install --ignore-installed -r requirements_frozen.txt
	@pip install --editable .


dev-run: .venv # Run the kaithem app.
	@cd ${ROOT_DIR}
	@${INTERPRETER} -m kaithem	

dev-update-dependencies: .venv # Install latest version of dependencies into the venv. New versions might break something!
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


root-install-system-dependencies: # Install non-python libraries using apt
	@sudo apt install python3-virtualenv scrot mpv lm-sensors  python3-netifaces python3-gst-1.0  gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad  swh-plugins  tap-plugins  caps   gstreamer1.0-plugins-ugly fluidsynth libfluidsynth3 gstreamer1.0-pocketsphinx x42-plugins baresip gstreamer1.0-opencv  gstreamer1.0-vaapi python3-opencv

root-use-pipewire-jack: # Reconfigure a Pi system or similar to not write to the SD so much.
	@cd ${ROOT_DIR}
	@bash ./scripts/install-pipewire-jack.sh



root-install-sd-protection: # Reconfigure a Pi system or similar to not write to the SD so much.
	@cd ${ROOT_DIR}
	@bash ./scripts/install-kaithem.sh

root-install-kiosk: # Sets up a pi(or similar) as a kiosk machine pointing to KIOSK_HOMEPAGE(default is kaithem at localhost:8002)
	@cd ${ROOT_DIR}
	@bash ./scripts/install-kaithem.sh

root-install-kaithem: root-install-system-dependencies # Install kaithem to run as KAITHEM_USER. Only one user at a time can run at boot.
	@cd ${ROOT_DIR}
	@echo "Kaithem will be installed to /home/$(id -un $KAITHEM_UID)/kaithem/.venv"
	@bash ./scripts/install-kaithem.sh

root-install-linux-tweaks: root-install-sd-protection root-use-pipewire-jack # Installs assorted tweaks to the Linux system.  Only use on dedicated devices.
	@cd ${ROOT_DIR}
	@bash ./scripts/install-kaithem.sh

root-kioskify: root-install-sd-protection root-use-pipewire-jack root-install-linux-tweaks root-install-kaithem # INstall kaithem, kiosk, and all config tweaks. Only use on dedicated devices.
	@echo "Making this system into a Kaithem based kiosk.  Please restart when done"

root-max-volume-at-boot: #Install a service that sets the max volume at boot, running on the kaithem user.
	@cd ${ROOT_DIR}
	@sudo -u $(KAITHEM_USER) bash ./scripts/max-volume.sh

root-enable-anon-mqtt: # Set up an MQTT broker for anonymous login acccess
	@cd ${ROOT_DIR}
	@bash ./scripts/setup-anon-mosquitto.sh