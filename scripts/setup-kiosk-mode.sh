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
sudo -u $(id -un $KAITHEM_UID) dbus-launch gsettings set org.gnome.desktop.screensaver lock-delay 3600
sudo -u $(id -un $KAITHEM_UID) dbus-launch gsettings set org.gnome.desktop.screensaver lock-enabled false
sudo -u $(id -un $KAITHEM_UID) dbus-launch gsettings set org.gnome.desktop.screensaver idle-activation-enabled false


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