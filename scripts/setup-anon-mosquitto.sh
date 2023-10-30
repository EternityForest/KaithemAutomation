set -e
set -x

# Require root
if [ "$(id -u)" -ne 0 ]; then
        echo 'This script must be run by root' >&2
        exit 1
fi


apt-get -y install mosquitto

cat << "EOF" >> /etc/mosquitto/conf.d/kaithem.conf
persistance false
allow_anonymous true
EOF

systemctl restart mosquitto.service
