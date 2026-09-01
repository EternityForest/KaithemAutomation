#!/bin/bash
mkdir -p /dev/shm/kiosk-temp-config
mkdir -p /dev/shm/kiosk-temp-cache

export XDG_CONFIG_HOME=/dev/shm/kiosk-temp-config
export XDG_CACHE_HOME=/dev/shm/kiosk-temp-cache
export HOME=/dev/shm/kiosk-temp-home

mkdir -p $XDG_CONFIG_HOME
mkdir -p $XDG_CACHE_HOME
mkdir -p $HOME

echo "Waiting for server to be available"
# In theory chrome retry should be enough but it's not so wait
wget --retry-connrefused --waitretry=1 --read-timeout=1800 --quiet --timeout=1800 -t 0 $KIOSK_URL

echo "Found server or timed out, starting chromium"

# --no-sandbox needed for docker


while true
do
    if chromium  --kiosk  --no-sandbox --start-fullscreen --disable-features=TouchpadOverscrollHistoryNavigation --disable-restore-session-state --start-maximized --noerrdialogs --disable-translate --disable-extensions --disable-apps --disable-component-extensions-with-background-pages --auto-accept-camera-and-microphone-capture --no-first-run --fast --fast-start --disable-infobars --disable-features=TranslateUI --autoplay-policy=no-user-gesture-required --no-default-browser-check --disk-cache-size=48000000 --no-first-run --simulate-outdated-no-au='Tue, 31 Dec 2099 23:59:59 GMT' $KIOSK_URL; then
        echo "Restarting because of error in Chromium"
    else
        echo "Exiting due to sucessful chrome exit"
        break
    fi
done
