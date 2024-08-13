#!/bin/bash
#   __    ___     ___           _            _   _             
#  / _\  /   \   / _ \_ __ ___ | |_ ___  ___| |_(_) ___  _ __  
#  \ \  / /\ /  / /_)/ '__/ _ \| __/ _ \/ __| __| |/ _ \| '_ \ 
#  _\ \/ /_//  / ___/| | | (_) | ||  __/ (__| |_| | (_) | | | |
#  \__/___,'   \/    |_|  \___/ \__\___|\___|\__|_|\___/|_| |_|
                                                             

# Try and make the SD card or other root disk not wear out, without affecting anything the user would
# notice too much
###################################################################################################

set -x
set -e


# Require root
if [ "$(id -u)" -ne 0 ]; then
        echo 'This script must be run by root' >&2
        exit 1
fi

# Use the KAITHEM_UID variable to set a user ID that will be running the code.
# 1000 is the default on almost all Linux systems
[ -z "$KAITHEM_UID" ] && KAITHEM_UID=1000

[ -z "$KAITHEM_USER" ] && KAITHEM_USER=$(id -un $KAITHEM_UID)


# X11 still exists even though Wayland is defayult
cd "$(dirname "${BASH_SOURCE[0]}")"

# No more swap to wear the disk!!!
! sudo apt-get purge -y dphys-swapfile

systemctl mask systemd-update-utmp.service
systemctl mask systemd-random-seed.service
systemctl disable systemd-update-utmp.service
systemctl disable systemd-random-seed.service

! systemctl disable systemd-readahead-collect.service
! systemctl disable systemd-readahead-replay.service

mkdir -p /home/$(id -un $KAITHEM_UID)/.local/state

! rm -rf  /home/$(id -un $KAITHEM_UID)/.local/state/wireplumber/
mkdir -p /var/run/$(id -un $KAITHEM_UID)-wireplumber-state/
# Make it look like it's in the same place so we can get to it easily
ln -s /var/run/$(id -un $KAITHEM_UID)-wireplumber-state  /home/$(id -un $KAITHEM_UID)/.local/state/wireplumber





# Xsession errors is a big offender for wrecking down your disk with writes
sed -i s/'ERRFILE=\$HOME\/\.xsession\-errors'/'ERRFILE\=\/var\/log\/\$KAITHEM_USER\-xsession\-errors'/g /etc/X11/Xsession


cat << EOF > /etc/logrotate.d/xsession
/var/log/$KAITHEM_USER-xsession-errors {
  rotate 2 
  daily
  compress
  missingok
  notifempty
}
EOF

! rm  /home/$(id -un $KAITHEM_UID)/.xsession-errors
# Make it look like it's in the same place so we can get to it easily
ln -s /var/log/ember-xsession-errors /home/$(id -un $KAITHEM_UID)/.xsession-errors


#/run should already be tmpfs on non-insane setups

#Before we cover it up, remove whats already there so it doesn't waste space forever
! rm /home/$(id -un $KAITHEM_UID)/.cache/lxsession/LXDE-pi/run.log

mkdir -p /home/$(id -un $KAITHEM_UID)/.cache/lxsession/

cat << EOF > /etc/systemd/system/home-$(id -un $KAITHEM_UID)-.cache-lxsession.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/home/$(id -un $KAITHEM_UID)/.cache/lxsession/
Type=tmpfs
Options=defaults,noatime,nosuid,nodev,noexec,mode=0755,size=32M,uid=$KAITHEM_UID

[Install]
WantedBy=multi-user.target
EOF

systemctl enable home-$(id -un $KAITHEM_UID)-.cache-lxsession.mount



! rm -rf /home/$(id -un $KAITHEM_UID)/.local/state/wireplumber/
mkdir -p /home/$(id -un $KAITHEM_UID)/.local/state/wireplumber/

cat << EOF > /etc/systemd/system/home-$(id -un $KAITHEM_UID)-.local-state-wireplumber.mount
[Unit]
Description=Flash saver ramdisk
Before=local-fs.target

[Mount]
What=tmpfs
Where=/home/$(id -un $KAITHEM_UID)/.local/state/wireplumber/
Type=tmpfs
Options=defaults,noatime,nosuid,nodev,noexec,mode=0777,size=32M,uid=$KAITHEM_UID

[Install]
WantedBy=multi-user.target
EOF

systemctl enable home-$(id -un $KAITHEM_UID)-.cache-lxsession.mount



cat << EOF > /etc/logrotate.d/lxsessionrunlog
/home/$(id -un $KAITHEM_UID)/.cache/lxsession/LXDE-pi/run.log {
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
Options=defaults,noatime,nosuid,nodev,mode=1777,size=786M

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


###################################################################################################
# Random seed, ensure HW rand is used because we might be disabling the SW entropy saving


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



# This salt will hopefully add some confusion in case the HWRNG is backdoored
# Since we aren't savibg randomness every hour
dd if=/dev/random of=/etc/random-salt bs=256 count=1 > /dev/null
date +%s%N >> /etc/random-salt


cat << EOF > /usr/bin/ember-random-seed.sh
#!/bin/bash
# Make things still random even when we get rid of the old random seed service
# By using HW randomness instead

#If the on chip hwrng isn't random, this might actually help if there is a real RTC installed.
date +%s%N > /dev/random

# Use the on chip HW RNG if it is available
if [ -e /dev/hwrng ] ; then
dd if=/dev/hwrng of=/dev/random bs=256 count=1 > /dev/null
else
dd if=/dev/random of=/dev/random bs=32 count=1 > /dev/null
fi

cat /etc/random-salt > /dev/random

#HWRNG might have unpredictable timing, no reason not to use the timer again.
#Probably isn't helping much but maybe makes paranoid types feel better?
date +%s%N > /dev/random

#The RNG should already be well seeded, but the systemd thing needs to think its doing something
touch /var/lib/systemd/random-seed
chmod 700 /var/lib/systemd/random-seed
dd bs=1 count=32K if=/dev/urandom of=/var/lib/systemd/random-seed > /dev/null
touch /run/cprng-seeded
EOF

systemctl enable ember-random-seed