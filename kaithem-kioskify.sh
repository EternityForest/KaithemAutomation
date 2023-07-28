#!/bin/bash

# This script turns a fresh Pi OS or similar image into a Kaithem embedded controller.  It is a stripped down version
# of code developed for the EmberOS project, which is on hold because I'm busy and hoping NixOS gets ready for prime time soon.



sudo apt-get install -y git python3 python3-pip



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



# Misc setup
##############################################

# Systemd all the way
sudo apt-get -y purge rsyslog

# Embedded PC disk protector

! systemctl disable systemd-readahead-collect.service
! systemctl disable systemd-readahead-replay.service


#Eliminate the apt-daily updates that were the suspected cause of periodic crashes in real deployments
sudo systemctl mask apt-daily-upgrade
sudo systemctl mask apt-daily.service
sudo systemctl mask apt-daily.timer

systemctl mask systemd-update-utmp.service
systemctl mask systemd-random-seed.service
systemctl disable systemd-update-utmp.service
systemctl disable systemd-random-seed.service
sudo systemctl disable apt-daily-upgrade.timer
sudo systemctl disable apt-daily.timer
sudo systemctl disable apt-daily.service


# Howerver DO update time zones and certs
#####################

cat << EOF >> /etc/systemd/system/ember-update.timer
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

cat << EOF >> /etc/systemd/system/ember-update.service
[Unit]
Description=EmberOS minimal updater, just the stuff that will break without it
[Service] 

Type=simple
ExecStart=/bin/bash /usr/bin/ember-update.sh
Type=oneshot
EOF

cat << EOF >> /usr/bin/ember-update.sh
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
cat << EOF >> /usr/lib/systemd/system.conf.d/20-emberos-watchdog.conf
# This file is part of EmberOS, it enables the hardware watchdog to allow recovery from
# total system crashes
[Manager]
RuntimeWatchdogSec=15
EOF




## Utils you can probably expect to want
#########################################################################

apt-get -y install onboard kmag qjackctl
apt-get -y install gnome-screenshot gnome-system-monitor gnome-logs
apt-get -y install nmap robotfindskitten ncdu mc curl fatrace gstreamer1.0-tools evince  unzip
apt-get -y install vim-tiny units git wget htop lsof  git-lfs git-repair xloadimage iotop zenity rename sshpass nethogs
# For accessing CDs
apt-get -y install  python3-cdio
apt-get -y install abcde --no-install-recommends
apt-get -y install glyrc imagemagick libdigest-sha-perl vorbis-tools atomicparsley eject eyed3 id3 id3v2 mkcue normalize-audio vorbisgain
apt-get -y install k3b
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



## Kaithem  with optional features
##############################################################################################################

sudo apt -y install mpv libmpv-dev python3 cython3 build-essential python3-msgpack python3-future python3-serial  python3-tz  python3-dateutil  lm-sensors  python3-netifaces python3-jack-client  python3-gst-1.0  python3-libnacl  jack-tools  jackd2  gstreamer1.0-plugins-good  gstreamer1.0-plugins-bad  swh-plugins  tap-plugins  caps   gstreamer1.0-plugins-ugly  python3-psutil  fluidsynth libfluidsynth2  network-manager python3-paho-mqtt python3-dbus python3-lxml gstreamer1.0-pocketsphinx x42-plugins baresip autotalent libmpv-dev python3-dev  libbluetooth-dev libcap2-bin rtl-433  python3-toml  python3-rtmidi python3-pycryptodome  gstreamer1.0-opencv  gstreamer1.0-vaapi python3-pillow python3-scipy ffmpeg python3-skimage
python3 -m pip install tflite-runtime 

chown -R $(id -un 1000):$(id -un 1000) /home/$(id -un 1000)/kaithem
chmod -R 700 /home/$(id -un 1000)/kaithem

chmod 755 /home/$(id -un 1000)/opt/KaithemAutomation/kaithem/kaithem.py

chown -R $(id -un 1000):$(id -un 1000)  /home/$(id -un 1000)/opt/

cat << "EOF" >>  /usr/bin/ember-launch-kaithem
#!/bin/bash
# Systemd utterly fails at launching this unless we give it it's own little script.
# If we run it directly from the service, jsonrpc times out over and over again.
/usr/bin/pw-jack /usr/bin/python3 /home/$(id -un 1000)/opt/KaithemAutomation/kaithem/kaithem.py -c /home/$(id -un 1000)/kaithem/config.yaml
EOF

chmod 755 /usr/bin/ember-launch-kaithem


# Many of these settings are ignored now that kaithem does more automatically.
mkdir -p    /home/$(id -un 1000)/kaithem/system.mixer
cat << EOF >>   /home/$(id -un 1000)/kaithem/system.mixer/jacksettings.yaml
{jackDevice: '', jackMode: use, jackPeriodSize: 512, jackPeriods: 3, sharePulse: 'off',
  usbLatency: -1, usbPeriodSize: 512, usbPeriods: 3, usbQuality: 0, useAdditionalSoundcards: 'no'}
EOF


cat << EOF >> /home/$(id -un 1000)/kaithem/config.yaml
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

cat << EOF >> /etc/systemd/system/kaithem.service
[Unit]
Description=KaithemAutomation python based automation server
After=basic.target time-sync.target sysinit.service zigbee2mqtt.service pipewire.service
Type=simple


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

[Install]
WantedBy=multi-user.target
EOF


systemctl enable kaithem.service


## Start in Kiosk mode, Kaithem's opinionated way is to do signage through the web

###############################################################################################################################


# Bye bye to the screen savier.
gsettings set org.gnome.desktop.screensaver lock-delay 3600
gsettings set org.gnome.desktop.screensaver lock-enabled false
gsettings set org.gnome.desktop.screensaver idle-activation-enabled false


mkdir -p /home/$(id -un 1000)/.config/autostart/

cat << EOF >> /home/$(id -un 1000)/.config/autostart/kiosk.desktop
[Desktop Entry]
Name=EmberDefaultKiosk
Type=Application
Exec=/usr/bin/ember-kiosk-launch.sh http://localhost:8002 &
Terminal=false
EOF

sudo apt -y install chromium-browser unclutter

cat << EOF >> /home/$(id -un 1000)/.config/autostart/unclutter.desktop
[Desktop Entry]
Name=Unclutter
Type=Application
Exec=unclutter
Terminal=false
EOF


cat << 'EOF' >>  /usr/bin/ember-kiosk-launch.sh
#!/bin/bash
mkdir -p /dev/shm/kiosk-temp-config
mkdir -p /dev/shm/kiosk-temp-cache
export XDG_CONFIG_HOME=/dev/shm/kiosk-temp-config
export XDG_CACHE_HOME=/dev/shm/kiosk-temp-cache

while true
do

    if chromium-browser  --kiosk --window-size=1920,1080 --start-fullscreen --kiosk --noerrdialogs --disable-translate --disable-extensions --auto-accept-camera-and-microphone-capture --no-first-run --fast --fast-start --disable-infobars --disable-features=TranslateUI --autoplay-policy=no-user-gesture-required --no-default-browser-check --disk-cache-size=48000000 --no-first-run --simulate-outdated-no-au='Tue, 31 Dec 2099 23:59:59 GMT' $1; then
        echo "Restarting because of error in Chromium"
    else
        echo "Exiting due to sucessful chrome exit"
        break
    fi
done

EOF


chmod 755 /usr/bin/ember-kiosk-launch.sh

cat << EOF >>  /etc/lightdm/lightdm.conf
[SeatDefaults]
autologin-guest=false
autologin-user=$(id -un 1000)
autologin-user-timeout=0

EOF



## Switch to NetworkManager
####################################################################################################################################

# This little piece of old garbage crashes everything when it sees you have switched to networkmanager and can't find it's stuff,
# because it still runs and fills ram with log files.
! apt-get -y remove dhcpcd-gtk

apt-get -y install network-manager libnss3-tools ca-certificates nftables firewalld avahi-daemon avahi-utils radvd

apt-get -y install network-manager-gnome

! systemctl disable wpa_supplicant.service
! systemctl mask wpa_supplicant.service

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
cat << EOF >> /etc/NetworkManager/NetworkManager.conf
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
cat << EOF >> /etc/NetworkManager/system-connections/ethernet.nmconnection
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

## Switch to Pipewire
#####################################################################################################################
apt-get install -y pipewire libspa-0.2-jack pipewire-audio-client-libraries libspa-0.2-bluetooth 
apt-get remove -y pulseaudio-module-bluetooth 

! apt-get purge -y pipewire-media-session
apt-get -y install wireplumber


mkdir -p /etc/pipewire/media-session.d/
touch /etc/pipewire/media-session.d/with-pulseaudio

sudo touch /etc/pipewire/media-session.d/with-alsa
sudo cp /usr/share/doc/pipewire/examples/alsa.conf.d/99-pipewire-default.conf /etc/alsa/conf.d/

su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user  disable pulseaudio.socket' $(id -un 1000)

su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user  disable pulseaudio.service' $(id -un 1000)

# Can't get this to work. Leave it off and things will use the ALSA virtual device it makes.
su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user disable  pipewire-pulse' $(id -un 1000)





su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user enable wireplumber' $(id -un 1000)
su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user enable pipewire' $(id -un 1000)

su -c 'XDG_RUNTIME_DIR="/run/user/$UID" DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus" systemctl --user mask pulseaudio' $(id -un 1000)

mkdir -p /etc/pipewire/media-session.d/with
touch /etc/pipewire/media-session.d/with-jack
cp /usr/share/doc/pipewire/examples/ld.so.conf.d/pipewire-jack-*.conf /etc/ld.so.conf.d/
ldconfig



cat << EOF >> /etc/pipewire/jack.conf

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

cat << EOF >> /etc/pipewire/media-session.d/bluez-monitor.conf
properties = {
    bluez5.msbc-support = true
    bluez5.sbc-xq-support = true
}
EOF





# Add TMPFSes to make the SD card not wear out.
###################################################################################################



# Xsession errors is a big offender for wrecking down your disk with writes
sed -i s/'ERRFILE=\$HOME\/\.xsession\-errors'/'ERRFILE\=\/var\/log\/\$USER\-xsession\-errors'/g /etc/X11/Xsession

# Xsession errors is a big offender for wrecking down your disk with writes
sed -i s/'ERRFILE=\$HOME\/\.xsession\-errors'/'ERRFILE\=\/var\/log\/\$USER\-xsession\-errors'/g /etc/X11/Xsession

cat << EOF >> /etc/logrotate.d/xsession
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

cat << EOF >> /etc/systemd/system/ember-tmpfs-media.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/media
Type=tmpfs
Options=defaults,noatime,nosuid,nodev,noexec,mode=0755,size=1M
EOF

systemctl enable ember-tmpfs-media.mount

cat << EOF >> /etc/systemd/system/ember-tmpfs-mnt.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/mnt
Type=tmpfs
Options=defaults,noatime,nosuid,nodev,noexec,mode=0755,size=1M
EOF

systemctl enable ember-tmpfs-mnt.mount


cat << EOF >> /etc/systemd/system/ember-tmpfs-tmp.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/tmp
Type=tmpfs
Options=defaults,noatime,nosuid,nodev,mode=1777,size=256M
EOF

systemctl enable ember-tmpfs-tmp.mount


cat << EOF >> /etc/systemd/system/ember-tmpfs-varlog.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/log
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0755,size=128M
EOF

systemctl enable ember-tmpfs-varlog.mount




cat << EOF >> /etc/systemd/system/ember-tmpfs-logrotate.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/lib/logrotate
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0755,size=32m
EOF


systemctl enable ember-tmpfs-logrotate.mount

cat << EOF >> /etc/systemd/system/ember-tmpfs-sudo.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/lib/sudo
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0700,size=8m
EOF

systemctl enable ember-tmpfs-sudo.mount



cat << EOF >> /etc/systemd/system/ember-tmpfs-systemd.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/lib/systemd
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0755,size=64m
EOF

systemctl enable ember-tmpfs-systemd.mount



cat << EOF >> /etc/systemd/system/ember-tmpfs-chrony.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/lib/chrony
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0755,size=8m
EOF

systemctl enable ember-tmpfs-chrony.mount


cat << EOF >> /etc/systemd/system/ember-tmpfs-vartmp.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/tmp
Type=tmpfs
Options=defaults,noatime,nosuid,mode=1777,size=128M
EOF

systemctl enable ember-tmpfs-vartmp.mount


cat << EOF >> /etc/systemd/system/ember-tmpfs-nm.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/var/lib/NetworkManager
Type=tmpfs
Options=defaults,noatime,nosuid,mode=0700,size=64M
EOF

systemctl enable ember-tmpfs-nm.mount

