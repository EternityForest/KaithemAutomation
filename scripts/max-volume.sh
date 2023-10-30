#!/bin/bash

cat << "EOF" > maxvolume.service
[Unit]
After=wireplumber.service pipewire-media-session.service
Description=Set pipewire audio level to 100%

[Service]
ExecStart=/bin/amixer set Master 100%
Type=OneShot

[Install]
WantedBy=default.target
EOF

systemctl --user edit --full --force maxvolume.service
systemctl --user enable --now maxvolume.service
