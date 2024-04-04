#!/bin/bash

## Install Kaithem, with all optional features.
## Runs as your user
## This doesn't install system dependencies, it is meant to be run from the Makefile

##############################################################################################################

# Don't need to install any system packages, the makefile does it for us.

set -x
set -e

mkdir -p ~/kaithem

! deactivate

if [ ! -d ~/kaithem/.venv ]; then
    virtualenv --system-site-packages ~/kaithem/.venv
else
    echo "Found venv"
fi

~/kaithem/.venv/bin/python -m pip install --upgrade -r requirements.txt
! ~/kaithem/.venv/bin/python -m pip uninstall kaithem -y
~/kaithem/.venv/bin/python setup.py install --force


cat << EOF > ~/kaithem/config.yaml
site-data-dir: ~/kaithem
ssl-dir: ~/kaithem/ssl
save-before-shutdown: yes
autosave-state: 2 hours
worker-threads: 16
http-thread-pool: 16
https-thread-pool: 4

#The port on which web pages will be served. The default port is 443, but we use 8001 in case you are running apache or something.
https-port : 8001
#The port on which unencrypted web pages will be served. The default port is 80, but we use 8001 in case you are running apache or something.
http-port : 8002

audio-paths:
    - __default__
EOF


mkdir -p ~/.config/systemd/user/
cat << EOF > ~/.config/systemd/user/kaithem.service
[Unit]
Description=KaithemAutomation python based automation server
After=time-sync.target sysinit.service mosquitto.service zigbee2mqtt.service pipewire.service multi-user.target graphical.target pipewire-media-session.service wireplumber.service


[Service]
TimeoutStartSec=0
ExecStart=/usr/bin/pw-jack /home/%u/kaithem/.venv/bin/python -m kaithem -c /home/%u/kaithem/config.yaml
Restart=on-failure
RestartSec=15
Type=simple

[Install]
WantedBy=default.target
EOF

systemctl --user enable --now kaithem.service
