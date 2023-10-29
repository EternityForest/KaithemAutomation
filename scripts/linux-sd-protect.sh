#!/bin/bash
#   __    ___     ___           _            _   _             
#  / _\  /   \   / _ \_ __ ___ | |_ ___  ___| |_(_) ___  _ __  
#  \ \  / /\ /  / /_)/ '__/ _ \| __/ _ \/ __| __| |/ _ \| '_ \ 
#  _\ \/ /_//  / ___/| | | (_) | ||  __/ (__| |_| | (_) | | | |
#  \__/___,'   \/    |_|  \___/ \__\___|\___|\__|_|\___/|_| |_|
                                                             

# Try and make the SD card or other root disk not wear out, without affecting anything the user would
# notice too much
###################################################################################################

# Require root
if [ "$(id -u)" -ne 0 ]; then
        echo 'This script must be run by root' >&2
        exit 1
fi

# X11 still exists even though Wayland is defayult
cd "$(dirname "${BASH_SOURCE[0]}")"

systemctl mask systemd-update-utmp.service
systemctl mask systemd-random-seed.service
systemctl disable systemd-update-utmp.service
systemctl disable systemd-random-seed.service

! systemctl disable systemd-readahead-collect.service
! systemctl disable systemd-readahead-replay.service



! rm -rf  /home/$(id -un 1000)/.local/state/wireplumber/
mkdir -p /var/run/$(id -un 1000)-wireplumber-state/
# Make it look like it's in the same place so we can get to it easily
ln -s /var/run/$(id -un 1000)-wireplumber-state  /home/$(id -un 1000)/.local/state/wireplumber





# Xsession errors is a big offender for wrecking down your disk with writes
sed -i s/'ERRFILE=\$HOME\/\.xsession\-errors'/'ERRFILE\=\/var\/log\/\$USER\-xsession\-errors'/g /etc/X11/Xsession


cat << EOF > /etc/logrotate.d/xsession
/var/log/$USER-xsession-errors {
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
