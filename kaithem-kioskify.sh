#!/bin/bash


#   _  __     _ _   _                      _  ___           _    _  __        
#  | |/ /    (_) | | |                    | |/ (_)         | |  (_)/ _|       
#  | ' / __ _ _| |_| |__   ___ _ __ ___   | ' / _  ___  ___| | ___| |_ _   _  
#  |  < / _` | | __| '_ \ / _ \ '_ ` _ \  |  < | |/ _ \/ __| |/ / |  _| | | | 
#  | . \ (_| | | |_| | | |  __/ | | | | | | . \| | (_) \__ \   <| | | | |_| | 
#  |_|\_\__,_|_|\__|_| |_|\___|_| |_| |_| |_|\_\_|\___/|___/_|\_\_|_|  \__, | 
#                                                                       __/ | 
#                                                                      |___/  

# This script turns a fresh Pi OS or similar image into a Kaithem embedded controller.  It is a stripped down version
# of code developed for the EmberOS project, which is on hold because I'm busy and hoping NixOS gets ready for prime time soon.
# Source error handling, leave this in place
set -x
set -e



mkdir -p /home/$(id -un 1000)/kioskify-setup

sudo apt update

sudo apt-get install -y git git-lfs python3 python3-pip

git lfs pull

## User perms
#####################################################################3
! sudo usermod -a -G dialout $(id -un 1000)
! sudo usermod -a -G serial $(id -un 1000)
! sudo usermod -a -G pulse-access $(id -un 1000)
! sudo usermod -a -G bluetooth $(id -un 1000)
! sudo usermod -a -G audio $(id -un 1000)
! sudo usermod -a -G plugdev $(id -un 1000)
! sudo usermod -a -G sudo $(id -un 1000)
! sudo usermod -a -G lpadmin $(id -un 1000)
! sudo usermod -a -G adm $(id -un 1000)
! sudo usermod -a -G rtkit $(id -un 1000)


#    ___ _                              
#   / __\ | ___  __ _ _ __  _   _ _ __  
#  / /  | |/ _ \/ _` | '_ \| | | | '_ \ 
# / /___| |  __/ (_| | | | | |_| | |_) |
# \____/|_|\___|\__,_|_| |_|\__,_| .__/ 
#                                |_|    

## Get rid of really big packages we don't need that are mostly nonfree
####################################################################################################################

# Move most of the deletion up front. Otherwise  it will get in the way and slow down the whole build.
! apt purge -y libpam-chksshpwd
! apt purge -y valgrind

! apt purge -y wolfram-engine wolframscript
! apt purge -y sonic-pi-samples
#apt-get -y install libreoffice-draw libreoffice-writer libreoffice-calc
! apt purge -y nuscratch
! apt purge -y scratch2
! apt purge -y scratch3
! apt purge -y scratch
! apt purge -y minecraft-pi
! apt purge -y python-minecraftpi
! apt purge -y realvnc-vnc-viewer
! apt purge -y gpicview
! apt purge -y oracle-java8-jdk
! apt purge -y oracle-java7-jdk
! apt purge -y tcsh
! apt purge -y smartsim

# I would like to get rid of this but people seem to like it... leave it on distros that have it
# ! apt-get -y purge firefox


# Old versions
! apt purge -y gcc-7
! apt purge -y gcc-8
! apt purge -y gcc-9

! apt purge -y ^dillo$  ^idle3$  ^smartsim$ ^sonic-pi$  ^epiphany-browser$  ^python-minecraftpi$ ^bluej$ 
! apt purge -y ^greenfoot$  ^greenfoot-unbundled$  ^claws-mail$ ^claws-mail-i18n$

! apt purge -y code-the-classics
! apt purge -y openjdk-11-jdk
! apt purge -y openjdk-11-jdk-headless
! apt purge -y bluej
! apt purge -y rpi-wayland

# Might need to use this if you get chrome file chooser crashes.  Should already be gone at start
! apt purge -y xdg-desktop-portal

! pip3 uninstall mu-editor

! rm -r /opt/Wolfram
! rm -r /usr/share/code-the-classics
! rm -r /home/$(id -nu 1000)/MagPi/*.pdf
! rm -r /home/$(id -nu 1000)/Bookshelf/Beginners*.pdf

# No more swap to wear the disk!!!
! sudo apt-get purge -y dphys-swapfile



apt autoremove -y --purge



#         _          
#   /\/\ (_)___  ___ 
#  /    \| / __|/ __|
# / /\/\ \ \__ \ (__ 
# \/    \/_|___/\___|
                   

# Misc setup
##############################################



cat << EOF > /etc/security/limits.conf
@audio   -  rtprio     95
@audio   -  memlock    unlimited
@audio   -  priority   -20
EOF


#raspi-config nonint do_ssh 0
! raspi-config nonint do_spi 0
! raspi-config nonint do_i2c 0
! raspi-config nonint do_camera 0
! raspi-config nonint do_overscan 1
! raspi-config nonint do_memory_split 128

# Systemd all the way
sudo apt-get -y purge rsyslog

#Eliminate the apt-daily updates that were the suspected cause of periodic crashes in real deployments
sudo systemctl mask apt-daily-upgrade
sudo systemctl mask apt-daily.service
sudo systemctl mask apt-daily.timer

sudo systemctl disable apt-daily-upgrade.timer
sudo systemctl disable apt-daily.timer
sudo systemctl disable apt-daily.service

# Remove SSH warning

! rm -rf /etc/profile.d/sshpwd.sh
! rm -rf /etc/xdg/lxsession/LXDE-pi/sshpwd.sh
! rm -rf /etc/xdg/autostart/pprompt.desktop


# Howerver DO update time zones and certs
#####################

cat << EOF > /etc/systemd/system/ember-update.timer
[Unit]
Description=EmberOS minimal updater, just the stuff that will break without it
RefuseManualStart=no # Allow manual starts
RefuseManualStop=no # Allow manual stops 

[Timer]
#Execute job if it missed a run due to machine being off
Persistent=yes
OnCalendar=*-*-01 02:00:00
Unit=ember-update.service

[Install]
WantedBy=timers.target
EOF

cat << EOF > /etc/systemd/system/ember-update.service
[Unit]
Description=EmberOS minimal updater, just the stuff that will break without it
[Service] 

Type=simple
ExecStart=/bin/bash /usr/bin/ember-update.sh
Type=oneshot
EOF

cat << EOF > /usr/bin/ember-update.sh
#!/bin/bash
yes | apt update
apt install ca-certificates
apt install tzdata
EOF

chmod 755 /usr/bin/ember-update.sh
systemctl enable ember-update.timer


## Watchdog for reliability

mkdir -p  /usr/lib/systemd/system.conf.d/

#Set up the watchdog timer to handle really bad crashes
# This can make it nt even boot if you set a bad time value...
cat << EOF > /usr/lib/systemd/system.conf.d/20-emberos-watchdog.conf
# This file is part of EmberOS, it enables the hardware watchdog to allow recovery from
# total system crashes
[Manager]
RuntimeWatchdogSec=15
EOF





#        _   _ _ _ _   _           
#  /\ /\| |_(_) (_) |_(_) ___  ___ 
# / / \ \ __| | | | __| |/ _ \/ __|
# \ \_/ / |_| | | | |_| |  __/\__ \
#  \___/ \__|_|_|_|\__|_|\___||___/
                                 

## Utils you can probably expect to want
#########################################################################


apt-get -y install onboard nmap robotfindskitten ncdu mc curl fatrace gstreamer1.0-tools evince  unzip xdotool neofetch
apt-get -y install vim-tiny units git wget htop lsof  git-lfs git-repair xloadimage iotop zenity rename sshpass nethogs dstat sysstat

# For accessing CDs
apt-get -y install  python3-cdio
apt-get -y install abcde --no-install-recommends
apt-get -y install glyrc imagemagick libdigest-sha-perl vorbis-tools atomicparsley eject eyed3 id3 id3v2 mkcue normalize-audio vorbisgain

# This lits us capture frames from DSLRs and the like
sudo apt-get -y install gphoto2 python3-gphoto2cffi
sudo apt-get -y  install libexif12 libgphoto2-6 libgphoto2-port12 libltdl7 gtkam entangle
#Need for cheap USB wifis
apt-get install -y ppp usb-modeswitch wvdial
# Control smart USB hubs per-port power, usb HID relays
apt-get -y install uhubctl usbrelay
apt-get -y install python3-pip libhidapi-libusb0 libxcb-xinerama0
# Gotta have this one
apt-get -y install kdeconnect nuntius

# IPod stuff
sudo apt-get -y install ifuse
sudo apt-get -y install libimobiledevice-utils
# Printerie
apt-get -y install cups cups-ipp-utils cups-core-drivers system-config-printer printer-driver-brlaser
#HPs scanner drivers
sudo apt-get -y install hplip hplip-gui sane sane-utils xsane


## GUI Apps
apt-get -y install  kmag qjackctl k3b git-cola
apt-get -y install gnome-screenshot gnome-system-monitor gnome-logs


## Kaithem  with optional features
##############################################################################################################

# Pretty sure the compiled version is going to be faster
sudo apt-get -y install python3-tornado

# Numpy is unhappy without this on latest pi os??
sudo apt-get install libatlas-base-dev libjasper-dev


sudo apt -y install scrot mpv libmpv-dev python3 cython3 build-essential python3-msgpack python3-future python3-serial  python3-tz  python3-dateutil  lm-sensors  python3-netifaces python3-jack-client  python3-gst-1.0  python3-libnacl  jack-tools  jackd2  gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad  swh-plugins  tap-plugins  caps   gstreamer1.0-plugins-ugly  python3-psutil  fluidsynth libfluidsynth2  network-manager python3-paho-mqtt python3-dbus python3-lxml gstreamer1.0-pocketsphinx x42-plugins baresip autotalent libmpv-dev python3-dev  libbluetooth-dev libcap2-bin rtl-433  python3-toml  python3-rtmidi python3-pycryptodome  gstreamer1.0-opencv  gstreamer1.0-vaapi python3-pillow python3-scipy ffmpeg python3-skimage python3-setproctitle
python3 -m pip install tflite-runtime 

pip3 install aioesphomeapi
pip3 install esphome

mkdir -p /home/$(id -un 1000)/kaithem
chown -R $(id -un 1000):$(id -un 1000) /home/$(id -un 1000)/kaithem
chmod -R 700 /home/$(id -un 1000)/kaithem

chmod 755 /opt/KaithemAutomation/dev_run.py


cat << "EOF" >  /usr/bin/ember-launch-kaithem
#!/bin/bash
# Systemd utterly fails at launching this unless we give it it's own little script.
# If we run it directly from the service, jsonrpc times out over and over again.
/usr/bin/pw-jack /usr/bin/python3 /opt/KaithemAutomation/dev_run.py -c /home/$(id -un 1000)/kaithem/config.yaml
EOF

chmod 755 /usr/bin/ember-launch-kaithem


# Many of these settings are ignored now that kaithem does more automatically.
mkdir -p    /home/$(id -un 1000)/kaithem/system.mixer
cat << EOF >   /home/$(id -un 1000)/kaithem/system.mixer/jacksettings.yaml
{jackMode: use}
EOF


cat << EOF > /home/$(id -un 1000)/kaithem/config.yaml
site-data-dir: ~/kaithem
ssl-dir: ~/kaithem/ssl
save-before-shutdown: yes
autosave-state: 2 hours
worker-threads: 16
http-thread-pool: 4
https-thread-pool: 16

#The port on which web pages will be served. The default port is 443, but we use 8001 in case you are running apache or something.
https-port : 8001
#The port on which unencrypted web pages will be served. The default port is 80, but we use 8001 in case you are running apache or something.
http-port : 8002

audio-paths:
    - /usr/share/tuxpaint/sounds
    - /usr/share/public.media/
    - __default__
EOF

cat << EOF > /etc/systemd/system/kaithem.service
[Unit]
Description=KaithemAutomation python based automation server
After=basic.target time-sync.target sysinit.service zigbee2mqtt.service pipewire.service graphical.target pipewire-media-session.service


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
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus"
Environment="XDG_RUNTIME_DIR=/run/user/1000"
Environment="DISPLAY=:0"

#This may cause some issues but I think it's a better way to go purely because of
#The fact that we can use PipeWire instead of managing jack, without any conflicts.

#Also, node red runs as pi/user 1000, lets stay standard.
User=1000
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
if [ ! -f /home/$(id -un 1000)/kaithem/system.mixer/presets/ ]; then

mkdir -p /home/$(id -un 1000)/kaithem/system.mixer/presets/

cat << EOF > /home/$(id -un 1000)/kaithem/system.mixer/presets/default.yaml
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



#        _           _    
#   /\ /(_) ___  ___| | __
#  / //_/ |/ _ \/ __| |/ /
# / __ \| | (_) \__ \   < 
# \/  \/|_|\___/|___/_|\_\
                        

## Start in Kiosk mode, Kaithem's opinionated way is to do signage through the web

###############################################################################################################################


# HW Acceleration
# sudo apt-get -y install libgles2-mesa libgles2-mesa-dev xorg-dev


# Bye bye to the screen savier.
gsettings set org.gnome.desktop.screensaver lock-delay 3600
gsettings set org.gnome.desktop.screensaver lock-enabled false
gsettings set org.gnome.desktop.screensaver idle-activation-enabled false


mkdir -p /home/$(id -un 1000)/.config/autostart/

cat << EOF > /home/$(id -un 1000)/.config/autostart/kiosk.desktop
[Desktop Entry]
Name=EmberDefaultKiosk
Type=Application
Exec=/usr/bin/ember-kiosk-launch.sh http://localhost:8002 &
Terminal=false
EOF

sudo apt -y install chromium-browser unclutter

cat << EOF > /home/$(id -un 1000)/.config/autostart/unclutter.desktop
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

# Try to not use 4k because that is slow
if xrandr | grep -q "1920x1080"; then
    DISPLAY=:0 xrandr -s 1920x1080
fi


# We don't do sound here, we intercept in kaithem so we have remote control of the effects
export PIPEWIRE_NODE=dummy_name


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
autologin-user=$(id -un 1000)
autologin-user-timeout=0

EOF


#      __     _                      _                                             
#   /\ \ \___| |___      _____  _ __| | __ /\/\   __ _ _ __   __ _  __ _  ___ _ __ 
#  /  \/ / _ \ __\ \ /\ / / _ \| '__| |/ //    \ / _` | '_ \ / _` |/ _` |/ _ \ '__|
# / /\  /  __/ |_ \ V  V / (_) | |  |   </ /\/\ \ (_| | | | | (_| | (_| |  __/ |   
# \_\ \/ \___|\__| \_/\_/ \___/|_|  |_|\_\/    \/\__,_|_| |_|\__,_|\__, |\___|_|   
#                                                                  |___/           

## Switch to NetworkManager
####################################################################################################################################

# This little piece of old garbage crashes everything when it sees you have switched to networkmanager and can't find it's stuff,
# because it still runs and fills ram with log files.
! apt-get -y remove dhcpcd-gtk

apt-get -y install network-manager libnss3-tools ca-certificates avahi-daemon avahi-utils radvd

apt-get -y install network-manager-gnome

! systemctl disable wpa_supplicant.service
! systemctl mask wpa_supplicant.service


# Now we are going to get rid of any legacy wpa-supplicant type stuff and use NetworkManager
# Unfortunately Pi still uses this stuff so we really do need it.

cat << EOF > /usr/bin/import_from_wpa_config.py
#!/usr/bin/python3

import subprocess
import re
import os
import configparser
import uuid

# Note: Will Not Work with PiWiz!!! They do some dhcpcd stuff.

n_re = r'network\s*=\s*{([\w\s=\"-]*?)}'

country_re = 'country\s*=\s*"?(...?)"?[\s$]'




if os.path.exists("/etc/wpa_supplicant/wpa_supplicant.conf"):
    with open("/etc/wpa_supplicant/wpa_supplicant.conf",'r') as f:
        s=f.read()


template = """
# This file has been imported from a wpa_supplicant configuration
# DO NOT MANUALLY CHANGE THIS FILE. CHANGES WILL BE OVERWRITTEN.
# IF YOU COPY THE FILE CONTENTS, GET RID OF THIS MARKER LINE OR
# iT WILL BE DELETED BY THE IMPORTER.
# imported_marker = b2bdb0b4-11da-40f2-b121-e50a1fe6a7d9

[connection]
#You can change that name
id=YourWifiNameHere
uuid=f671d4c3-2ae0-417d-ad5a-9bc1d040b0ec
type=wifi
#Fake timestamp to make it think it has connected before,
#And attemp to avoid the "only one attempt then give up" problem
timestamp=123456
permissions=


[wifi]
mac-address-blacklist=
mode=infrastructure

ssid=YourWifiNameHere

#Just straight up delete this whole section
#To connect to unsecured networks
[wifi-security]
auth-alg=open
key-mgmt=wpa-psk
psk=YourWifiPasswordHere

[ipv4]
dns-search=
method=auto

#You can do DHCP but also add manual static addresses
#addresses=192.168.0.200/24

[ipv6]
addr-gen-mode=eui64
dns-search=
method=auto
"""
nsuid = "9cf4c103-f2bf-4ff3-a122-91cda420186b"


valid_uuids = {}


# Set the regulatory domain
for i in re.findall(country_re,s):
    subprocess.call(['iw','reg','set', i])


try:
    os.makedirs("/etc/NetworkManager/system-connections/",mode=16877)
except Exception:
    pass

for i in re.findall(n_re,s):
    c = configparser.ConfigParser()
    c.read_string("[d]\r\n"+i)
    c = c['d']
    if 'ssid' in c and 'psk' in c:
        t2 = template.replace('YourWifiNameHere',c['ssid'].replace('"','') if c['ssid'].startswith('"') else c['ssid'])
        t2 = t2.replace('YourWifiPasswordHere',c['psk'])
        u = uuid.uuid5(uuid.UUID(nsuid),c['ssid']+ "/" + c['psk'] )
        valid_uuids[str(u)] = True
        t2 = t2.replace('f671d4c3-2ae0-417d-ad5a-9bc1d040b0ec', str(u))

        path = "/etc/NetworkManager/system-connections/"+"imported_wpaconf_donotedit"+c['ssid'].replace("/",'_').replace('"','').replace(" ",'_')


        if os.path.exists(path):
            with open(path) as f:
                if t2==f.read():
                    continue

        with open(path,'w') as f:
            f.write(t2)

        if not os.stat(path).st_mode == '0o100600':
            os.chmod(path, 0o100600)

for i in list(os.listdir("/etc/NetworkManager/system-connections/")):
    d = os.path.join("/etc/NetworkManager/system-connections/", i)

    with open(d,'r') as f:
        s = f.read()
    
    if "b2bdb0b4-11da-40f2-b121-e50a1fe6a7d9" in s:
        # Now we know it was made be this app

        valid = 0
        for j in valid_uuids:
            if j in s:
                # We found one of the UUIDs that we know comes from one of our files
                valid = 1
        if not valid:
             os.remove(d)
EOF


cat << EOF > /etc/systemd/system/import_wpa_conf_to_nm.service
[Unit]
Description=Import any networks found in a wpa_supplicant file to NetworkManager
Before=NetworkManager.service
After=raspberrypi-net-mods.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/bin/import_from_wpa_config.py

[Install]
WantedBy=NetworkManager.service
EOF

chmod 755 /usr/bin/import_from_wpa_config.py
chmod 744 /etc/systemd/system/import_wpa_conf_to_nm.service

systemctl enable import_wpa_conf_to_nm.service
systemctl start import_wpa_conf_to_nm.service


systemctl enable NetworkManager.service



# Which one? Both? Seems to work!
! systemctl disable dhcpcd.service
! systemctl disable dhcpcd5.service
! systemctl mask dhcpcd.service
! systemctl mask dhcpcd5.service

! systemctl unmask wpa_supplicant.service


! sudo apt purge -y openresolv


# WiFi power save is not really that big of a savings
# Get rid of the privacy mac for stability reasons
cat << EOF > /etc/NetworkManager/NetworkManager.conf
[main]
plugins=ifupdown,keyfile

[ifupdown]
managed=true

[device]
wifi.scan-rand-mac-address=no

[connection]
wifi.powersave = 2

[connection-mac-randomization]
ethernet.cloned-mac-address=permanent
wifi.cloned-mac-address=permanent 

EOF


# Ethernet settings
cat << EOF > /etc/NetworkManager/system-connections/ethernet.nmconnection
[connection]
id=Ethernet
uuid=8874a940-b7d6-3b50-9cfb-031801810ab4
type=ethernet
autoconnect-priority=-100

timestamp=123456
permissions=

[ethernet]
mac-address-blacklist=
auto-negotiate=yes

[ipv4]
dns-search=
method=auto

[ipv6]
addr-gen-mode=eui64
dns-search=
method=auto
EOF


#    ___ _                     _          
#   / _ (_)_ __   _____      _(_)_ __ ___ 
#  / /_)/ | '_ \ / _ \ \ /\ / / | '__/ _ \
# / ___/| | |_) |  __/\ V  V /| | | |  __/
# \/    |_| .__/ \___| \_/\_/ |_|_|  \___|
#         |_|                             

## Switch to Pipewire
#####################################################################################################################
apt-get install -y pipewire libspa-0.2-jack pipewire-audio-client-libraries libspa-0.2-bluetooth 
apt-get remove -y pulseaudio-module-bluetooth 

mkdir -p /etc/pipewire/media-session.d/
touch /etc/pipewire/media-session.d/with-pulseaudio

sudo touch /etc/pipewire/media-session.d/with-alsa
sudo cp /usr/share/doc/pipewire/examples/alsa.conf.d/99-pipewire-default.conf /etc/alsa/conf.d/

su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user  disable pulseaudio.socket' $(id -un 1000)

su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user  disable pulseaudio.service' $(id -un 1000)

# Can't get this to work. Leave it off and things will use the ALSA virtual device it makes.
# Some things have it already disabled.
! su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user disable  pipewire-pulse' $(id -un 1000)


su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user enable pipewire' $(id -un 1000)

su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user mask pulseaudio' $(id -un 1000)

mkdir -p /etc/pipewire/media-session.d/with
touch /etc/pipewire/media-session.d/with-jack
cp /usr/share/doc/pipewire/examples/ld.so.conf.d/pipewire-jack-*.conf /etc/ld.so.conf.d/
ldconfig



cat << EOF > /etc/pipewire/jack.conf

# JACK client config file for PipeWire version "0.3.24" #

context.properties = {
    ## Configure properties in the system.
    #mem.warn-mlock  = false
    #mem.allow-mlock = true
    #mem.mlock-all   = false
    log.level        = 0
}

context.spa-libs = {
    #<factory-name regex> = <library-name>
    #
    # Used to find spa factory names. It maps an spa factory name
    # regular expression to a library name that should contain
    # that factory.
    #
    support.* = support/libspa-support
}

context.modules = [
    #{   name = <module-name>
    #    [ args = { <key> = <value> ... } ]
    #    [ flags = [ [ ifexists ] [ nofail ] ]
    #}
    #
    # Loads a module with the given parameters.
    # If ifexists is given, the module is ignored when it is not found.
    # If nofail is given, module initialization failures are ignored.
    #
    #
    # Uses RTKit to boost the data thread priority.
    {   name = libpipewire-module-rtkit
        args = {
            #nice.level   = -11
            #rt.prio      = 88
            #rt.time.soft = 200000
            #rt.time.hard = 200000
        }
        flags = [ ifexists nofail ]
    }

    # The native communication protocol.
    {   name = libpipewire-module-protocol-native }

    # Allows creating nodes that run in the context of the
    # client. Is used by all clients that want to provide
    # data to PipeWire.
    {   name = libpipewire-module-client-node }

    # Allows applications to create metadata objects. It creates
    # a factory for Metadata objects.
    {   name = libpipewire-module-metadata }
]

jack.properties = {
     node.latency = 128/48000
     #jack.merge-monitor  = false
     #jack.short-name     = false
     #jack.filter-name    = false
}

EOF

cat << EOF > /etc/pipewire/media-session.d/bluez-monitor.conf
properties = {
    bluez5.msbc-support = true
    bluez5.sbc-xq-support = true
}
EOF



#   __    ___     ___           _            _   _             
#  / _\  /   \   / _ \_ __ ___ | |_ ___  ___| |_(_) ___  _ __  
#  \ \  / /\ /  / /_)/ '__/ _ \| __/ _ \/ __| __| |/ _ \| '_ \ 
#  _\ \/ /_//  / ___/| | | (_) | ||  __/ (__| |_| | (_) | | | |
#  \__/___,'   \/    |_|  \___/ \__\___|\___|\__|_|\___/|_| |_|
                                                             

# Try and make the SD card not wear out.
###################################################################################################


systemctl mask systemd-update-utmp.service
systemctl mask systemd-random-seed.service
systemctl disable systemd-update-utmp.service
systemctl disable systemd-random-seed.service

! systemctl disable systemd-readahead-collect.service
! systemctl disable systemd-readahead-replay.service



# Xsession errors is a big offender for wrecking down your disk with writes
sed -i s/'ERRFILE=\$HOME\/\.xsession\-errors'/'ERRFILE\=\/var\/log\/\$USER\-xsession\-errors'/g /etc/X11/Xsession

# Xsession errors is a big offender for wrecking down your disk with writes
sed -i s/'ERRFILE=\$HOME\/\.xsession\-errors'/'ERRFILE\=\/var\/log\/\$USER\-xsession\-errors'/g /etc/X11/Xsession

cat << EOF > /etc/logrotate.d/xsession
/var/log/ember-xsession-errors {
  rotate 2 
  daily
  compress
  missingok
  notifempty
}
EOF

! rm  /home/$(id -un 1000)/.xsession-errors
# Make it look like it's in the same place so we can get to it easily
ln -s /var/log/ember-xsession-errors /home/$(id -un 1000)/.xsession-errors


#/run should already be tmpfs on non-insane setups

#Before we cover it up, remove whats already there so it doesn't waste space forever
! rm /home/$(id -un 1000)/.cache/lxsession/LXDE-pi/run.log

mkdir -p /home/$(id -un 1000)/.cache/lxsession/

cat << EOF > /etc/systemd/system/home-$(id -un 1000)-.cache-lxsession.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/home/$(id -un 1000)/.cache/lxsession/
Type=tmpfs
Options=defaults,noatime,nosuid,nodev,noexec,mode=0755,size=32M

[Install]
WantedBy=multi-user.target
EOF

systemctl enable home-$(id -un 1000)-.cache-lxsession.mount


cat << EOF > /etc/logrotate.d/lxsessionrunlog
/home/$(id -un 1000)/.cache/lxsession/LXDE-pi/run.log {
  rotate 2 
  daily
  compress
  missingok
  notifempty
}
EOF



cat << EOF > /etc/systemd/system/media.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/media
Type=tmpfs
Options=defaults,noatime,nosuid,nodev,noexec,mode=0755,size=1M

[Install]
WantedBy=multi-user.target
EOF

systemctl enable media.mount

cat << EOF > /etc/systemd/system/mnt.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/mnt
Type=tmpfs
Options=defaults,noatime,nosuid,nodev,noexec,mode=0755,size=1M

[Install]
WantedBy=multi-user.target
EOF

systemctl enable mnt.mount


cat << EOF > /etc/systemd/system/tmp.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/tmp
Type=tmpfs
Options=defaults,noatime,nosuid,nodev,mode=1777,size=256M

[Install]
WantedBy=multi-user.target
EOF

systemctl enable tmp.mount


cat << EOF > /etc/systemd/system/var-log.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/log
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0755,size=128M

[Install]
WantedBy=multi-user.target
EOF

systemctl enable var-log.mount




cat << EOF > /etc/systemd/system/var-lib-logrotate.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/lib/logrotate
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0755,size=32m

[Install]
WantedBy=multi-user.target
EOF


systemctl enable var-lib-logrotate.mount

cat << EOF > /etc/systemd/system/var-lib-sudo.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/lib/sudo
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0700,size=8m

[Install]
WantedBy=multi-user.target
EOF

systemctl enable var-lib-sudo.mount



cat << EOF > /etc/systemd/system/var-lib-systemd.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/lib/systemd
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0755,size=64m

[Install]
WantedBy=multi-user.target
EOF

systemctl enable var-lib-systemd.mount



cat << EOF > /etc/systemd/system/var-lib-chrony.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/lib/chrony
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0755,size=8m

[Install]
WantedBy=multi-user.target
EOF

systemctl enable var-lib-chrony.mount


cat << EOF > /etc/systemd/system/var-tmp.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/tmp
Type=tmpfs
Options=defaults,noatime,nosuid,mode=1777,size=128M

[Install]
WantedBy=multi-user.target
EOF

systemctl enable var-tmp.mount


cat << EOF > /etc/systemd/system/var-lib-NetworkManager.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/lib/NetworkManager
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0700,size=64M

[Install]
WantedBy=multi-user.target
EOF

systemctl enable var-lib-NetworkManager.mount



#########################################################
# Install SD card monitoring utility


cd /home/$(id -un 1000)/kioskify-setup


if [ `uname -m` == "aarch64" ]; then

# This is the program that lets us get the SanDisk industrial health data.

wget -nc  https://github.com/Ognian/sdmon/releases/download/v0.4.2/sdmon-arm64.tar.gz
tar zxf sdmon-arm64.tar.gz
mv sdmon /usr/bin
chmod 755 /usr/bin/sdmon 

fi


if [ `uname -m` == "armv7l" ]; then

# This is the program that lets us get the SanDisk industrial health data.

wget -nc  https://github.com/Ognian/sdmon/releases/download/v0.4.2/sdmon-armv7.tar.gz
tar zxf sdmon-armv7.tar.gz
mv sdmon /usr/bin
chmod 755 /usr/bin/sdmon 

fi



cat << EOF > /etc/systemd/system/ember-sdmon-cache.timer
[Unit]
Description=Check SD wear status on supported industrial cards
RefuseManualStart=no # Allow manual starts
RefuseManualStop=no # Allow manual stops 

[Timer]
Persistent=no
OnCalendar=daily
Unit=ember-sdmon-cache.service

[Install]
WantedBy=timers.target
EOF

cat << EOF > /etc/systemd/system/ember-sdmon-cache.service
[Unit]
Description=Check SD wear status on supported industrial cards

[Service] 
Type=simple
ExecStart=/bin/bash /usr/bin/ember-sdmon-cache.sh
Type=oneshot

[Install]
WantedBy=multi-user.target
EOF

cat << EOF > /usr/bin/ember-sdmon-cache.sh
#!/bin/bash
mkdir -p /run/sdmon-cache
sdmon /dev/mmcblk0 > /dev/shm/sdmon_cache_mmcblk0~
chmod 755 /dev/shm/sdmon_cache_mmcblk0~
mv /dev/shm/sdmon_cache_mmcblk0~ /run/sdmon-cache/mmcblk0
EOF

cat << EOF > /usr/bin/get-sdmon-remaining.py
#!/usr/bin/python3
import os
import json
if os.path.exists("/dev/shm/sdmon_cache_mmcblk0"):
  with open("/dev/shm/sdmon_cache_mmcblk0") as f:
    d = json.load(f)
  if "enduranceRemainLifePercent" in d:
    print(str(d["enduranceRemainLifePercent"])+'%')
  elif "healthStatusPercentUsed" in d:
    print(str(100 - d["healthStatusPercentUsed"])+'%')
  else:
    print("unknown %")

EOF


chmod 755 /usr/bin/ember-sdmon-cache.sh
systemctl enable ember-sdmon-cache.timer



if [ `uname -m` == "aarch64" ]; then
systemctl enable ember-sdmon-cache.timer
fi


if [ `uname -m` == "armv7l" ]; then
systemctl enable ember-sdmon-cache.timer
fi


###################################################################################################
# Random seed


cat << EOF > /etc/systemd/system/ember-random-seed.service
[Unit]
Description=make systemd random seeding work, and whatever else needs to happen at boot for RO systems.
After=systemd-remount-fs.service
Before=sysinit.target nmbd.service smbd.service apache2.service systemd-logind.service
RequiresMountsFor=/etc/ /var/log/
DefaultDependencies=no

[Service]
Type=oneshot
ExecStart=/bin/bash /usr/bin/ember-random-seed.sh

[Install]
WantedBy=sysinit.target
EOF

cat << EOF > /usr/bin/ember-random-seed.sh
#!/bin/bash
# Make things still random even when we get rid of the old random seed service
# By using HW randomnes instead

#If the on chip hwrng isn't random, this might actually help if there is a real RTC installed.
date +%s%N > /dev/random

# Use the on chip HW RNG if it is available
if [ -e /dev/hwrng ] ; then
dd if=/dev/hwrng of=/dev/random bs=256 count=1 > /dev/null
else
dd if=/dev/random of=/dev/random bs=32 count=1 > /dev/null
fi

#HWRNG might have unpredictable timing, no reason not to use the timer again.
#Probably isn't helping much but maybe makes paranoid types feel better?
date +%s%N > /dev/random

#The RNG should already be well seeded, but the systemd thing needs to think its doing something
touch /var/lib/systemd/random-seed
chmod 700 /var/lib/systemd/random-seed
dd bs=1 count=32K if=/dev/urandom of=/var/lib/systemd/random-seed > /dev/null
touch /run/cprng-seeded
EOF

chmod 755 /usr/bin/ember-update.sh
systemctl enable ember-random-seed