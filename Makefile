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

USER:= $(shell id -un)


export USER
export KIOSK_HOME
export ROOT_DIR

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


.PHONY: root-install-zrok
root-install-zrok: # Install or update Zrok for remote access
	@cd ${ROOT_DIR}
	@bash ./scripts/install-zrok.sh

.PHONY: user-setup-zrok-sharing
user-setup-zrok-sharing: # Create an account with zrok
	@cd ${ROOT_DIR}
	@bash ./scripts/setup-zrok.sh


.PHONY: user-set-global-pipewire-conf
user-set-global-pipewire-conf:
	@echo ${USER}
	@cd ${ROOT_DIR}
	@mkdir -p /home/${USER}/.config/pipewire/
	@cat ./scripts/pipewire.conf > /home/${USER}/.config/pipewire/pipewire.conf
	@systemctl --user restart pipewire wireplumber

.PHONY: user-install-kaithem
user-start-kaithem-at-boot: # Install kaithem to run as your user. Note that it only runs when you are logged in.
	@cd ${ROOT_DIR}
	@echo "Kaithem will be installed with a systemd user service."
	@bash ./scripts/install-kaithem-service.sh

.PHONY: user-max-volume-at-boot
user-max-volume-at-boot: #Install a service that sets the max volume when you log in.
	@cd ${ROOT_DIR}
	@bash ./scripts/max-volume.sh


.PHONY: user-kaithem-force-restart
user-kaithem-force-restart: # Force kill the process and restart it.
	@killall -9 kaithem
	@systemctl --user restart kaithem.service

.PHONY: user-restart-pipewire
user-restart-pipewire:
	@echo "Tries to restart everything, including some that may fail because they're not installed"
	@systemctl --user restart pipewire pipewire-pulse wireplumber


.PHONY: user-kaithem-status
user-kaithem-status: # Get the status of the running kaithem instance
	@systemctl --user status kaithem.service

# todo Escape undercores in md files, handsdown doesn't escape them ye
.PHONY: dev-build-docs
dev-build-docs:
	@handsdown -i kaithem/api/ -o kaithem/src/docs/api


.PHONY: dev-count-lines
dev-count-lines: # Line count summary
	@poetry run pygount --format=summary --names-to-skip="*.min.js" --folders-to-skip="thirdparty,data,__pycache__" kaithem/


.PHONY: dev-file-lines
dev-file-lines: # Show files sorted by line count
	@poetry run pygount --names-to-skip="*.min.js" --folders-to-skip="thirdparty,data,__pycache__" kaithem/ | sort -nr -


.PHONY: root-install-system-dependencies
root-install-system-dependencies: # Install non-python libraries using apt
	@sudo apt install mpv python3-opencv lm-sensors python3-gst-1.0  gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad  swh-plugins  tap-plugins  caps   gstreamer1.0-plugins-ugly libfluidsynth3 gstreamer1.0-pocketsphinx x42-plugins gstreamer1.0-opencv  gstreamer1.0-vaapi gstreamer1.0-pipewire

.PHONY: root-use-pipewire-jack
root-use-pipewire-jack: # Make JACK clients work with pipewire
	@cd ${ROOT_DIR}
	@bash ./scripts/install-pipewire-jack.sh


.PHONY: root-install-sd-protection
root-install-sd-protection: # Reconfigure a Pi system or similar to not write to the SD so much.  User specific things apply to KAITHEM_USER
	@cd ${ROOT_DIR}
	@bash ./scripts/linux-sd-protect.sh

.PHONY: root-install-kiosk
root-install-kiosk: # Sets up a pi(or similar) as a kiosk machine pointing to KIOSK_HOMEPAGE(default is kaithem at localhost:8002)
	@cd ${ROOT_DIR}
	@bash ./scripts/setup-kiosk-mode.sh

.PHONY: root-install-linux-tweaks
root-install-linux-tweaks: root-install-sd-protection root-use-pipewire-jack # Installs assorted tweaks to the Linux system.  Only use on dedicated devices. User specific things apply to KAITHEM_USER
	@cd ${ROOT_DIR}
	@bash ./scripts/linux-tweaks.sh


.PHONY: root-uninstall-bloatware
oot-uninstall-bloatware: # Uninstall random junk you probably don't want on an embedded system.
	@cd ${ROOT_DIR}
	@bash ./scripts/uninstall-bloatware.sh


.PHONY: root-install-utilities
root-install-utilities: # Install random junk you might want, like drivers for obscure devices and troubleshooting utils
	@cd ${ROOT_DIR}
	@bash ./scripts/install-utilities.sh


.PHONY: root-enable-anon-mqtt
root-enable-anon-mqtt: # Set up an MQTT broker for anonymous login acccess
	@cd ${ROOT_DIR}
	@bash ./scripts/setup-anon-mosquitto.sh


