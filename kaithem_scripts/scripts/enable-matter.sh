

# Use the KAITHEM_UID variable to set a user ID that
# will be running the code.
# 1000 is the default on almost all Linux systems

# Run as the kaithem user due to needing to put the data
# in the kaithem folder for ease of backup

sudo DEBIAN_FRONTEND=noninteractive apt -y install docker.io

! docker pull ghcr.io/matter-js/python-matter-server:8.1.2

[ -z "$KAITHEM_UID" ] && KAITHEM_UID=1000

[ -z "$KAITHEM_USER" ] && KAITHEM_USER=$(id -un $KAITHEM_UID)

KAITHEM_GRP=$(id -g $KAITHEM_UID)

mkdir -p /home/$(id -un $KAITHEM_UID)/kaithem/python-matter-server

chown $KAITHEM_UID  /home/$(id -un $KAITHEM_UID)/kaithem/python-matter-server
chgrp $KAITHEM_GRP  /home/$(id -un $KAITHEM_UID)/kaithem/python-matter-server

cat << EOF > /etc/systemd/system/kaithem-matter-server.service

[Unit]
Description=My Docker Container Service
After=docker.service
Before=kaithem.service
Requires=docker.service

[Service]
Restart=on-failure
ExecStart=/usr/bin/docker run --rm --user $(id -u $KAITHEM_UID):$(id -g $KAITHEM_UID) \
  --name %n \
  --security-opt apparmor=unconfined \
  -v /home/$(id -un $KAITHEM_UID)/kaithem/python-matter-server:/data \
  -v /run/dbus:/run/dbus:ro \
  --network=host \
  ghcr.io/matter-js/python-matter-server:8.1.2 --storage-path /data --paa-root-cert-dir /data/credentials --bluetooth-adapter 0

Type=simple

[Install]
WantedBy=multi-user.target

EOF
systemctl daemon-reload
systemctl enable kaithem-matter-server.service
systemctl restart kaithem-matter-server.service

exit 0