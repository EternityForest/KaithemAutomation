#!/bin/bash

#        _           _    
#   /\ /(_) ___  ___| | __
#  / //_/ |/ _ \/ __| |/ /
# / __ \| | (_) \__ \   < 
# \/  \/|_|\___/|___/_|\_\
                        

## Start in Kiosk mode, Kaithem's opinionated way is to do signage through the web

###############################################################################################################################

set -x
set -e

# Require root
if [ "$(id -u)" -ne 0 ]; then
        echo 'This script must be run by root' >&2
        exit 1
fi

# Ensure we are in the right dir
cd "$(dirname "${BASH_SOURCE[0]}")"


# Bye bye to the screen savier.
sudo -u $(id -un $KAITHEM_UID) gsettings set org.gnome.desktop.screensaver lock-delay 3600
sudo -u $(id -un $KAITHEM_UID) gsettings set org.gnome.desktop.screensaver lock-enabled false
sudo -u $(id -un $KAITHEM_UID) gsettings set org.gnome.desktop.screensaver idle-activation-enabled false


mkdir -p /home/$(id -un $KAITHEM_UID)/.config/autostart/

cat << EOF > /home/$(id -un $KAITHEM_UID)/.config/autostart/kiosk.desktop
[Desktop Entry]
Name=EmberDefaultKiosk
Type=Application
Exec=/usr/bin/ember-kiosk-launch.sh $KIOSK_HOME &
Terminal=false
EOF

sudo apt -y install chromium-browser unclutter

cat << EOF > /home/$(id -un $KAITHEM_UID)/.config/autostart/unclutter.desktop
[Desktop Entry]
Name=Unclutter
Type=Application
Exec=unclutter
Terminal=false
EOF


cat << 'EOF' >  /usr/bin/ember-kiosk-launch.sh
#!/bin/bash

# Needed so xrandr doesn't get overwritten with something and mess up resolution
sleep 15
mkdir -p /dev/shm/kiosk-temp-config
mkdir -p /dev/shm/kiosk-temp-cache
export DISPLAY=:0
export XDG_CONFIG_HOME=/dev/shm/kiosk-temp-config
export XDG_CACHE_HOME=/dev/shm/kiosk-temp-cache

# We don't do sound here, we intercept in kaithem so we have remote control of the effects
STATUS="$(systemctl is-active kaithem.service)"
if [ "${STATUS}" = "active" ]; then
    export PIPEWIRE_NODE=dummy_name
    echo "Running sound through Kaithem"
else 
    echo "Kaithem not enabled, running sound directly"  
    exit 1  
fi

while true
do
    if chromium-browser  --kiosk --window-size=1920,1080 --start-fullscreen --noerrdialogs --disable-translate --disable-extensions --auto-accept-camera-and-microphone-capture --no-first-run --fast --fast-start --disable-infobars --disable-features=TranslateUI --autoplay-policy=no-user-gesture-required --no-default-browser-check --disk-cache-size=48000000 --no-first-run --simulate-outdated-no-au='Tue, 31 Dec 2099 23:59:59 GMT' $1; then
        echo "Restarting because of error in Chromium"
    else
        echo "Exiting due to sucessful chrome exit"
        break
    fi
done

EOF


chmod 755 /usr/bin/ember-kiosk-launch.sh

cat << EOF >  /etc/lightdm/lightdm.conf
[SeatDefaults]
autologin-guest=false
autologin-user=$(id -un $KAITHEM_UID)
autologin-user-timeout=0
EOF


# Make the audio work out of the box.  This is where we intercept the Chromium kiosk audio
# But we do not want to overwrite an existig preset!
if [ ! -f /home/$(id -un $KAITHEM_UID)/kaithem/system.mixer/presets/ ]; then

mkdir -p /home/$(id -un $KAITHEM_UID)/kaithem/system.mixer/presets/

cat << EOF > /home/$(id -un $KAITHEM_UID)/kaithem/system.mixer/presets/default.yaml
PiKiosk:
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