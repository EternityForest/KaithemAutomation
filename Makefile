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
ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

export KAITHEM_UID
export KAITHEM_USER

ifndef KIOSK_HOME
KIOSK_HOME:="http://localhost:8002"
endif

export KIOSK_HOME
export ROOT_DIR

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
	@echo "user- commands affect your user"
	@echo
	@grep -E '^[a-zA-Z0-9\. -]+:.*#'  Makefile | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#'| fold -w 60 -s)\n\n"; done





${ROOT_DIR}/.venv: # Create the virtualenv in the project folder
	@cd ${ROOT_DIR}
	@virtualenv --system-site-packages .venv

${ROOT_DIR}/.isolated_venv: # Create the virtualenv in the project folder
	@cd ${ROOT_DIR}
	@virtualenv .isolated_venv


update: # Fetch new code into this project folder
	git pull

dev-make-venv: ${ROOT_DIR}/.venv ${ROOT_DIR}/.isolated_venv # Make the virtualenv in this project folder.
	@echo "Making venv if not present"

dev-install: dev-make-venv # Install Kaithem and all it's dependencies in the Venv.
	@cd ${ROOT_DIR}
	@.venv/bin/python -m pip install --ignore-installed -r requirements_frozen.txt
	@.venv/bin/python -m pip install --editable .

dev-run: # Run the kaithem app.
	@cd ${ROOT_DIR}
	@pw-jack .venv/bin/python -m kaithem	

dev-run-isolated: # Run the kaithem app.
	@cd ${ROOT_DIR}
	@pw-jack .isolated_venv/bin/python -m kaithem	

dev-update-dependencies: dev-make-venv # Install latest version of dependencies into the venv. New versions might break something!
	@cd ${ROOT_DIR}
	@.isolated_venv/bin/python -m pip install --ignore-installed  -U -r direct_dependencies.txt
	@.venv/bin/python -m pip install --ignore-installed  -U -r direct_dependencies.txt
	@.isolated_venv/bin/python -m pip freeze -l > requirements_frozen.txt
	# If kaithem itself installed here, avoid circular nonsense
	@sed -i '/.*kaithem.*/d' ./requirements_frozen.txt
	@.venv/bin/python -m pip install --ignore-installed -r requirements_frozen.txt

user-install-kaithem: # Install kaithem to run as your user. Note that it only runs when you are logged in.
	@cd ${ROOT_DIR}
	@echo "Kaithem will be installed to /home/$(id -un)/kaithem/.venv"
	@bash ./scripts/install-kaithem.sh

user-max-volume-at-boot: #Install a service that sets the max volume when you log in.
	@cd ${ROOT_DIR}
	@bash ./scripts/max-volume.sh


user-kaithem-force-restart: # Force kill the process and restart it.
	@killall -9 kaithem
	@systemctl --user restart kaithem.service

user-restart-pipewire:
	@echo "Tries to restart everything, including some that may fail because they're not installed"
	@systemctl --user restart pipewire pipewire-pulse wireplumber pipewire-media-session


user-kaithem-status: # Get the status of the running kaithem instance
	@systemctl --user status kaithem.service




root-install-system-dependencies: # Install non-python libraries using apt
	@sudo apt install python3-virtualenv scrot mpv lm-sensors  python3-netifaces python3-gst-1.0  gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad  swh-plugins  tap-plugins  caps   gstreamer1.0-plugins-ugly fluidsynth libfluidsynth3 gstreamer1.0-pocketsphinx x42-plugins baresip gstreamer1.0-opencv  gstreamer1.0-vaapi python3-opencv gstreamer1.0-pipewire
	
root-use-pipewire-jack: # Make JACK clients work with pipewire
	@cd ${ROOT_DIR}
	@bash ./scripts/install-pipewire-jack.sh

root-install-sd-protection: # Reconfigure a Pi system or similar to not write to the SD so much.  User specific things apply to KAITHEM_USER
	@cd ${ROOT_DIR}
	@bash ./scripts/linux-sd-protect.sh

root-install-kiosk: # Sets up a pi(or similar) as a kiosk machine pointing to KIOSK_HOMEPAGE(default is kaithem at localhost:8002)
	@cd ${ROOT_DIR}
	@bash ./scripts/setup-kiosk-mode.sh

root-install-linux-tweaks: root-install-sd-protection root-use-pipewire-jack # Installs assorted tweaks to the Linux system.  Only use on dedicated devices. User specific things apply to KAITHEM_USER
	@cd ${ROOT_DIR}
	@bash ./scripts/linux-tweaks.sh

root-enable-anon-mqtt: # Set up an MQTT broker for anonymous login acccess
	@cd ${ROOT_DIR}
	@bash ./scripts/setup-anon-mosquitto.sh


