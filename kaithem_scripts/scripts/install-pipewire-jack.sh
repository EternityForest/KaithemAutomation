#!/bin/bash

# This should allow all JACK apps to use Pipewire

set -x
set -e

# Require root
if [ "$(id -u)" -ne 0 ]; then
        echo 'This script must be run by root' >&2
        exit 1
fi


apt -y install pipewire-audio-client-libraries

cp /usr/share/doc/pipewire/examples/ld.so.conf.d/pipewire-jack-*.conf /etc/ld.so.conf.d/
ldconfig

echo "Log out and in again, or do 'kaithem-scripts user-restart-pipewire'"