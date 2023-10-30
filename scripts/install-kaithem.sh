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
cd /home/$(id -un $KAITHEM_UID)/kaithem


if [ ! -d /home/$(id -un $KAITHEM_UID)/kaithem/.venv ]; then
    su $(id -un $KAITHEM_UID) virtualenv --system-site-packages /home/$(id -un $KAITHEM_UID)/kaithem/.venv
fi

# As the $KAITHEM_UID user, in a virtualenv
su $(id -un $KAITHEM_UID) /home/$(id -un $KAITHEM_UID)/kaithem/.venv/bin/python -m pip install --ignore-installed -r /opt/KaithemAutomation/requirements_frozen.txt



cat << "EOF" >  /usr/bin/ember-launch-kaithem
#!/bin/bash
# Systemd utterly fails at launching this unless we give it it's own little script.
# If we run it directly from the service, jsonrpc times out over and over again.
# Since Kaithem has it's own volume stuff, do this hacky thing to fix pi insisting that 40% is the right setting.
/usr/bin/amixer set Master 100%
/usr/bin/pw-jack /home/$(id -un)/kaithem/.venv/bin/python /opt/KaithemAutomation/dev_run.py -c /home/$(id -un)/kaithem/config.yaml
EOF

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
ExecStart=/usr/bin/bash -o pipefail -c /usr/bin/ember-launch-kaithem
Restart=on-failure
RestartSec=15
OOMScoreAdjust=-800
Nice=-15
#Make it try to act like a GUI program if it can because some modules might
#make use of that.  Note that this is a bad hack hardcoding the UID.
#Pipewire breaks without it though.
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$KAITHEM_UID/bus"
Environment="XDG_RUNTIME_DIR=/run/user/$KAITHEM_UID"
Environment="DISPLAY=:0"

#This may cause some issues but I think it's a better way to go purely because of
#The fact that we can use PipeWire instead of managing jack, without any conflicts.

#Also, node red runs as pi/user $KAITHEM_UID, lets stay standard.
User=$KAITHEM_UID
#Bluetooth scannning and many other things will need this
#Setting the system time is used for integration with GPS stuff.
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_ADMIN CAP_NET_RAW CAP_SYS_TIME CAP_SYS_NICE
SecureBits=keep-caps

LimitRTPRIO= 95
LimitNICE= -20
LimitMEMLOCK= infinity
Type=simple

[Install]
WantedBy=multi-user.target
EOF

# Make the audio work out of the box.  This is where we intercept the Chromium kiosk audio
# But we do not want to overwrite an existig preset!
if [ ! -f /home/$(id -un $KAITHEM_UID)/kaithem/system.mixer/presets/ ]; then

mkdir -p /home/$(id -un $KAITHEM_UID)/kaithem/system.mixer/presets/

cat << EOF > /home/$(id -un $KAITHEM_UID)/kaithem/system.mixer/presets/default.yaml
Kiosk:
  channels: 2
  effects:
  - displayType: Fader
    help: The main fader for the channel
    id: f26c3ef7-61bf-4154-87b4-98eb874252ee
    params: {}
    type: fader
  fader: -1.5
  input: PipeWire ALSA [chromium-browser]
  level: -17.6
  mute: false
  output: bcm2835 Headphones
  soundFuse: 3
  type: audio
EOF

fi

systemctl enable kaithem.service
