#!/bin/bash

## Install Kaithem, with all optional features.
## Runs as your user
## This doesn't install system dependencies, it is meant to be run from the Makefile

##############################################################################################################

set -x
set -e

mkdir -p ~/kaithem


if [ ! -f ~/.local/bin/kaithem ]; then
    echo -e "\033[0;31mWarning: kaithem not found on path. Ensure that you have Kaithem installed.\033[0m"
fi

if [ ! -f ~/kaithem/config.yaml ]; then

cat << EOF > ~/kaithem/config.yaml
# Add your config here!

EOF

fi


mkdir -p ~/.config/systemd/user/

if [ ! -f ~/.config/systemd/user/kaithem.service ]; then

cat << EOF > ~/.config/systemd/user/kaithem.service
[Unit]
Description=KaithemAutomation python based automation server
After=time-sync.target sysinit.service mosquitto.service zigbee2mqtt.service pipewire.service multi-user.target graphical.target pipewire-media-session.service wireplumber.service


[Service]
TimeoutStartSec=0
ExecStart=/usr/bin/pw-jack /home/%u/.local/bin/kaithem
Restart=on-failure
RestartSec=15
Type=simple

[Install]
WantedBy=default.target
EOF

fi

systemctl --user enable --now kaithem.service
