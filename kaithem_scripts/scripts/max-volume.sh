#!/bin/bash

# Crappy hack
mkdir -p ~/.local/bin

cat << EOF >> ~/.local/bin/_maxvolume_hack
#!/bin/bash
# Awful hacks. We don't know what sets the volume too low or when it happens.

sleep 5
/bin/amixer set Master 100%
/bin/amixer -c 1 set PCM 100%
/bin/amixer -c 0 set PCM 100%
/bin/amixer set Headphone 100%
/bin/amixer set Speaker 100%

sleep 10
/bin/amixer set Master 100%
/bin/amixer -c 1 set PCM 100%
/bin/amixer -c 0 set PCM 100%
/bin/amixer set Headphone 100%
/bin/amixer set Speaker 100%

sleep 15
/bin/amixer set Master 100%
/bin/amixer -c 1 set PCM 100%
/bin/amixer -c 0 set PCM 100%
/bin/amixer set Headphone 100%
/bin/amixer set Speaker 100%

sleep 30
/bin/amixer set Master 100%
/bin/amixer -c 1 set PCM 100%
/bin/amixer -c 0 set PCM 100%
/bin/amixer set Headphone 100%
/bin/amixer set Speaker 100%

sleep 60
/bin/amixer set Master 100%
/bin/amixer -c 1 set PCM 100%
/bin/amixer -c 0 set PCM 100%
/bin/amixer set Headphone 100%
/bin/amixer set Speaker 100%

exit 0
EOF

chmod 755 ~/.local/bin/_maxvolume_hack

mkdir -p ~/.config/systemd/user/
cat << "EOF" > ~/.config/systemd/user/maxvolume.service
[Unit]
After=wireplumber.service pipewire-media-session.service
Description=Set pipewire audio level to 100%

[Service]
ExecStart=/bin/bash /home/%u/.local/bin/_maxvolume_hack
Type=OneShot

[Install]
WantedBy=default.target
EOF

systemctl --user enable --now maxvolume.service





