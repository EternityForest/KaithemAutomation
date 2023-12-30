#!/bin/bash


#   _  __     _ _   _                      _  ___           _    _  __        
#  | |/ /    (_) | | |                    | |/ (_)         | |  (_)/ _|       
#  | ' / __ _ _| |_| |__   ___ _ __ ___   | ' / _  ___  ___| | ___| |_ _   _  
#  |  < / _` | | __| '_ \ / _ \ '_ ` _ \  |  < | |/ _ \/ __| |/ / |  _| | | | 
#  | . \ (_| | | |_| | | |  __/ | | | | | | . \| | (_) \__ \   <| | | | |_| | 
#  |_|\_\__,_|_|\__|_| |_|\___|_| |_| |_| |_|\_\_|\___/|___/_|\_\_|_|  \__, | 
#                                                                       __/ | 
#                                                                      |___/  

# 

# This script turns a fresh Pi OS or similar image into a Kaithem embedded controller.

# This reconfigures a lot of things to optimally run a Chrome/Kaithem kiosk. Probably don't run this on a desktop
# unless you want it to mess with your settings.
# * Eliminate unneeded proprietary packages on Pi
# * Install troubleshooting utilities
# * Disable Wifi sleep and privacy MAC
# * Give lots of permissions to KAITHEM_UID
# * Remove rsyslog if present
# * Disable auto-update

set -x
set -e


# Require root
if [ "$(id -u)" -ne 0 ]; then
        echo 'This script must be run by root' >&2
        exit 1
fi

# Ensure we are in the right dir
cd "$(dirname "${BASH_SOURCE[0]}")"



mkdir -p /home/$(id -un $KAITHEM_UID)/kioskify-setup

sudo apt update

sudo apt-get install -y git git-lfs python3 python3-pip

git lfs pull

## User perms
#####################################################################3
! sudo usermod -a -G dialout $(id -un $KAITHEM_UID)
! sudo usermod -a -G serial $(id -un $KAITHEM_UID)
! sudo usermod -a -G pulse-access $(id -un $KAITHEM_UID)
! sudo usermod -a -G bluetooth $(id -un $KAITHEM_UID)
! sudo usermod -a -G audio $(id -un $KAITHEM_UID)
! sudo usermod -a -G plugdev $(id -un $KAITHEM_UID)
! sudo usermod -a -G sudo $(id -un $KAITHEM_UID)
! sudo usermod -a -G lpadmin $(id -un $KAITHEM_UID)
! sudo usermod -a -G adm $(id -un $KAITHEM_UID)
! sudo usermod -a -G rtkit $(id -un $KAITHEM_UID)


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
! apt purge -y kicad

# I would like to get rid of this but people seem to like it so much it will stir up trouble... leave it on distros that have it
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

# Might need to use this if you get chrome file chooser crashes.
# ! apt purge -y xdg-desktop-portal

! apt purge -y mu-editor

! rm -r /opt/Wolfram
! rm -r /usr/share/code-the-classics
! rm -r /home/$(id -nu $KAITHEM_UID)/MagPi/*.pdf
! rm -r /home/$(id -nu $KAITHEM_UID)/Bookshelf/Beginners*.pdf

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


sudo apt -y install zram-tools

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
! sudo apt-get -y purge rsyslog

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
RefuseManualStart=no
RefuseManualStop=no

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


apt-get -y install waypipe

apt-get -y install onboard nmap robotfindskitten ncdu mc curl fatrace gstreamer1.0-tools evince  unzip xdotool neofetch sqlite3
apt-get -y install vim-tiny jq units git wget htop lsof  git-lfs git-repair xloadimage iotop zenity rename sshpass nethogs dstat sysstat

# For accessing CDs
apt-get -y install  python3-cdio
apt-get -y install abcde --no-install-recommends
apt-get -y install glyrc imagemagick libdigest-sha-perl vorbis-tools atomicparsley eject eyed3 id3 id3v2 normalize-audio vorbisgain

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



#      __     _                      _                                             
#   /\ \ \___| |___      _____  _ __| | __ /\/\   __ _ _ __   __ _  __ _  ___ _ __ 
#  /  \/ / _ \ __\ \ /\ / / _ \| '__| |/ //    \ / _` | '_ \ / _` |/ _` |/ _ \ '__|
# / /\  /  __/ |_ \ V  V / (_) | |  |   </ /\/\ \ (_| | | | | (_| | (_| |  __/ |   
# \_\ \/ \___|\__| \_/\_/ \___/|_|  |_|\_\/    \/\__,_|_| |_|\__,_|\__, |\___|_|   
#                                                                  |___/           

## NetworkManager Config
####################################################################################################################################

# This little piece of old garbage crashes everything when it sees you have switched to networkmanager and can't find it's stuff,
# because it still runs and fills ram with log files.
! apt-get -y remove dhcpcd-gtk



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
type=ethernetcd "$(dirname "${BASH_SOURCE[0]}")"

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



#########################################################
# Install SD card monitoring utility


cd /home/$(id -un $KAITHEM_UID)/kioskify-setup


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
RefuseManualStart=no
RefuseManualStop=no

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

