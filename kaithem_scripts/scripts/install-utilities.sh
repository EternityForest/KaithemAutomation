#!/bin/bash

#        _   _ _ _ _   _           
#  /\ /\| |_(_) (_) |_(_) ___  ___ 
# / / \ \ __| | | | __| |/ _ \/ __|
# \ \_/ / |_| | | | |_| |  __/\__ \
#  \___/ \__|_|_|_|\__|_|\___||___/
                                 

## Utils you can probably expect to want
#########################################################################


apt-get -y install waypipe

apt-get -y install matchbox-keyboard

apt-get -y install nmap ncdu mc curl fatrace  unzip xdotool neofetch sqlite3
apt-get -y install vim-tiny jq units git wget htop lsof git-lfs git-repair xloadimage iotop zenity rename sshpass nethogs dstat sysstat

# Toys
apt-get -y install robotfindskitten cowsay figlet

# For accessing CDs
apt-get -y install  python3-cdio
apt-get -y install abcde --no-install-recommends
apt-get -y install glyrc libdigest-sha-perl vorbis-tools atomicparsley eject eyed3 id3 id3v2

# Media tools
apt-get -y install gstreamer1.0-tools jack-tools
apt-get -y install imagemagick normalize-audio vorbisgain

# This lits us capture frames from DSLRs and the like
sudo apt-get -y install gphoto2 python3-gphoto2cffi
sudo apt-get -y  install libexif12 libgphoto2-6 libgphoto2f-port12 libltdl7 gtkam entangle
#Need for cheap USB wifis
apt-get install -y ppp usb-modeswitch wvdial
# Control smart USB hubs per-port power, usb HID relays
apt-get -y install uhubctl usbrelay
apt-get -y install python3-pip libhidapi-libusb0 libxcb-xinerama0


# IPod stuff
sudo apt-get -y install ifuse
sudo apt-get -y install libimobiledevice-utils
# Printerie
apt-get -y install cups cups-ipp-utils cups-core-drivers system-config-printer printer-driver-brlaser
#HPs scanner drivers
sudo apt-get -y install hplip hplip-gui sane sane-utils xsane
