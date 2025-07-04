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


# if kaithem uid not set raise error
if [ -z "$KAITHEM_UID" ]; then
    echo "KAITHEM_UID not set"
    exit 1
fi

# don't allow root either
if [ "$KAITHEM_UID" -eq 0 ]; then
    echo "KAITHEM_UID cannot be root"
    exit 1
fi

#require kiosk home to be set
if [ -z "$KIOSK_HOME" ]; then
    echo "KIOSK_HOME not set"
    exit 1
fi

# Bye bye to the screen savier.
sudo -u $(id -un $KAITHEM_UID) dbus-launch gsettings set org.gnome.desktop.screensaver lock-delay 3600
sudo -u $(id -un $KAITHEM_UID) dbus-launch gsettings set org.gnome.desktop.screensaver lock-enabled false
sudo -u $(id -un $KAITHEM_UID) dbus-launch gsettings set org.gnome.desktop.screensaver idle-activation-enabled false


# Needed to undo screen saver on pi
if command -v raspi-config &> /dev/null; then
  sudo raspi-config nonint do_blanking 1
fi

# TODO autologon on non-lightdm systems.
mkdir -p /etc/lightdm

SESSION_CFG=""


# Make a backup
if [ -f /etc/lightdm/lightdm.conf ]; then
    sed /etc/lightdm/lightdm.conf -i -e "s/^\(#\|\)autologin-user=.*/autologin-user=$(id -un $KAITHEM_UID)/"
fi


# if rpi config exists
if command -v raspi-config &> /dev/null; then
  # Auto login
  sudo raspi-config nonint do_boot_behaviour B4
fi


# Remove SSH warning on the pi.  Redundantly done in linux tweaks.
if [ -f /etc/profile.d/sshpwd.sh ]; then
    rm -rf /etc/profile.d/sshpwd.sh
fi

if [ -f /etc/xdg/lxsession/LXDE-pi/sshpwd.sh ]; then
    rm -rf /etc/xdg/lxsession/LXDE-pi/sshpwd.sh
fi

if [ -f /etc/xdg/autostart/pprompt.desktop ]; then
    rm -rf /etc/xdg/autostart/pprompt.desktop
fi




mkdir -p /home/$(id -un $KAITHEM_UID)/.config/autostart/

cat << EOF > /home/$(id -un $KAITHEM_UID)/.config/autostart/kiosk.desktop
[Desktop Entry]
Name=EmberDefaultKiosk
Type=Application
Exec=/usr/bin/ember-kiosk-launch.sh $KIOSK_HOME &
Terminal=false
EOF

sudo apt -y install chromium-browser


cat << 'EOF' >  /usr/bin/ember-kiosk-launch.sh
#!/bin/bash
mkdir -p /dev/shm/kiosk-temp-config
mkdir -p /dev/shm/kiosk-temp-cache
export DISPLAY=:0
export XDG_CONFIG_HOME=/dev/shm/kiosk-temp-config
export XDG_CACHE_HOME=/dev/shm/kiosk-temp-cache

# if [ -e /run/user/1000/wayland-1 ] && [ ! -e /run/user/1000/wayland-0 ]; then
#   export WAYLAND_DISPLAY=wayland-1
# fi

# In theory chrome retry should be enough but it's not so wait
wget --retry-connrefused --waitretry=1 --read-timeout=480 --quiet --timeout=480 -t 0 $1

while true
do
    if chromium-browser  --kiosk --start-fullscreen --disable-features=TouchpadOverscrollHistoryNavigation --disable-restore-session-state --start-maximized --noerrdialogs --disable-translate --disable-extensions --auto-accept-camera-and-microphone-capture --no-first-run --fast --fast-start --disable-infobars --disable-features=TranslateUI --autoplay-policy=no-user-gesture-required --no-default-browser-check --disk-cache-size=48000000 --no-first-run --simulate-outdated-no-au='Tue, 31 Dec 2099 23:59:59 GMT' $1; then
        echo "Restarting because of error in Chromium"
    else
        echo "Exiting due to sucessful chrome exit"
        break
    fi
done

EOF


chmod 755 /usr/bin/ember-kiosk-launch.sh

