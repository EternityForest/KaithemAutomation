#!/bin/bash


# This reconfigures a lot of things to optimally run a Chrome/Kaithem kiosk or some other embedded thing.
# Probably don't run this on a desktop
# unless you want it to mess with your settings.

# The SD card protection stuff lives in another file.

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

wget -nc  https://github.com/Ognian/sdmon/releases/download/v0.9.0/sdmon-arm64.tar.gz
tar zxf sdmon-arm64.tar.gz
mv sdmon /usr/bin
chmod 755 /usr/bin/sdmon 

fi


if [ `uname -m` == "armv7l" ]; then

# This is the program that lets us get the SanDisk industrial health data.

wget -nc  https://github.com/Ognian/sdmon/releases/download/v0.9.0/sdmon-armv7.tar.gz
tar zxf sdmon-armv7.tar.gz
mv sdmon /usr/bin
chmod 755 /usr/bin/sdmon 

fi




if [ `uname -m` == "aarch64" ]; then

# This is the program that lets us get the SanDisk industrial health data.

wget -nc  https://github.com/darkhz/bluetuith/releases/download/v0.2.2/bluetuith_0.2.2_Linux_arm64.tar.gz
tar zxf bluetuith_0.2.2_Linux_arm64.tar.gz
mv bluetuith /usr/bin
chmod 755 /usr/bin/bluetuith 

fi

