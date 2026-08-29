
#!/bin/bash

# If you are looking at this to manually install,
# You probably also want to run debian_setup_dependencies.sh first


# network-manager has nmcli needed to get wifi status
# libnss-mdns is needed to get .local even with dicker host netwowking apparently
# ffmpeg used by chandler to inspect media metadata
# rsync needed for the build, it's also just incredibly common so we might as well leave it

apt install -y python3 mpv lm-sensors python3-gst-1.0  gstreamer1.0-plugins-good \
gstreamer1.0-plugins-bad gstreamer1.0-tools swh-plugins tap-plugins \
caps gstreamer1.0-plugins-ugly \
x42-plugins gstreamer1.0-vaapi gstreamer1.0-pipewire \
pipewire-jack gir1.2-gtk-3.0 \
python3-venv gstreamer1.0-libav network-manager libnss-mdns ffmpeg rsync \
libjack-jackd2-0
