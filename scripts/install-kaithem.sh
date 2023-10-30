#!/bin/bash

## Install Kaithem, with all optional features.
## Runs as user $KAITHEM_UID
## This doesn't install system dependencies, it is meant to be run from the Makefile

##############################################################################################################

# Don't need to install any system packages, the makefile does it for us.

set -x
set -e


# Require root
if [ "$(id -u)" -ne 0 ]; then
        echo 'This script must be run by root' >&2
        exit 1
fi


mkdir -p /home/$(id -un $KAITHEM_UID)/kaithem
chown -R $(id -un $KAITHEM_UID):$(id -un $KAITHEM_UID) /home/$(id -un $KAITHEM_UID)/kaithem
chmod -R 700 /home/$(id -un $KAITHEM_UID)/kaithem


mkdir -p /home/$(id -un $KAITHEM_UID)/kaithem


if [ ! -d /home/$(id -un $KAITHEM_UID)/kaithem/.venv ]; then
    sudo -u $(id -un $KAITHEM_UID) virtualenv --system-site-packages /home/$(id -un $KAITHEM_UID)/kaithem/.venv
fi

# As the $KAITHEM_UID user, in a virtualenv
sudo -u $(id -un $KAITHEM_UID) /home/$(id -un $KAITHEM_UID)/kaithem/.venv/bin/python -m pip install -U --ignore-installed -r requirements_frozen.txt
sudo -u $(id -un $KAITHEM_UID) /home/$(id -un $KAITHEM_UID)/kaithem/.venv/bin/python setup.py install


chmod 755 /usr/bin/ember-launch-kaithem


# Many of these settings are ignored now that kaithem does more automatically.
mkdir -p    /home/$(id -un $KAITHEM_UID)/kaithem/system.mixer
cat << EOF >   /home/$(id -un $KAITHEM_UID)/kaithem/system.mixer/jacksettings.yaml
{jackMode: use}
EOF


cat << EOF > /home/$(id -un $KAITHEM_UID)/kaithem/config.yaml
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
    - /usr/share/tuxpaint/sounds
    - __default__
EOF

cat << EOF > /etc/systemd/system/kaithem.service
[Unit]
Description=KaithemAutomation python based automation server
After=time-sync.target sysinit.service mosquitto.service zigbee2mqtt.service pipewire.service multi-user.target graphical.target pipewire-media-session.service wireplumber.service


[Service]
TimeoutStartSec=0
ExecStart=/usr/bin/pw-jack /home/$(id -un $KAITHEM_UID)/kaithem/.venv/bin/python -m kaithem -c /home/$(id -un $KAITHEM_UID)/kaithem/config.yaml
Restart=on-failure
RestartSec=15
# OOMScoreAdjust=-800
# Nice=-15

#Make it try to act like a GUI program if it can because some modules might
#make use of that.  Note that this is a bad hack hardcoding the UID.
# #Pipewire breaks without it though.
# Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$KAITHEM_UID/bus"
# Environment="XDG_RUNTIME_DIR=/run/user/$KAITHEM_UID"
# Environment="DISPLAY=:0"

# User=$(id -un $KAITHEM_UID)
#Bluetooth scannning and many other things will need this
#Setting the system time is used for integration with GPS stuff.
# AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_ADMIN CAP_NET_RAW CAP_SYS_TIME CAP_SYS_NICE
# SecureBits=keep-caps

# LimitRTPRIO= 95
# LimitNICE= -20
# LimitMEMLOCK= infinity
Type=simple

[Install]
WantedBy=multi-user.target
EOF


systemctl enable kaithem.service
systemctl restart kaithem.service

