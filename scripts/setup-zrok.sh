#!/bin/bash
set -x
set -e

# Generate a "reserved share", 
TOKEN=$(zrok reserve public localhost:8002 -j | jq -r ".token")

cat << EOF > ~/.config/systemd/user/kaithem-zrok-share.service
[Unit]
Description=Give Kaithem a public URL with zrok.
After=kaithem.service


[Service]
TimeoutStartSec=0
ExecStart=zrok share reserved --headless $TOKEN
Restart=on-failure
RestartSec=15
Type=simple

[Install]
WantedBy=default.target
EOF

systemctl --user enable kaithem-zrok-share.service
systemctl --user start kaithem-zrok-share.service
systemctl --user status kaithem-zrok-share.service

echo "Your URL is https://$TOKEN.share.zrok.io.  Service installed at ~/.config/systemd/user/kaithem-zrok-share.service"