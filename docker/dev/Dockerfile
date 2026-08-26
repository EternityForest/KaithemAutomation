FROM kaithem-build:dev

# Install the same runtime stuff as the app but keep the
# build tools around

# network-manager has nmcli needed to get wifi status
# libnss-mdns is needed to get .local even with dicker host netwowking apparently
# ffmpeg used by chandler to inspect media metadata
# rsync needed for the build, it's also just incredibly common so we might as well leave it

# Mount host-cached directories into the container during the build phase
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt install -y python3 mpv lm-sensors python3-gst-1.0  gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-tools swh-plugins tap-plugins \
    caps gstreamer1.0-plugins-ugly \
    x42-plugins gstreamer1.0-vaapi gstreamer1.0-pipewire \
    pipewire-jack gir1.2-gtk-3.0 \
    python3-venv gstreamer1.0-libav network-manager libnss-mdns ffmpeg rsync \
    libjack-jackd2-0

# The iceflow hack doesn't work with readonly images so
# Do it ahead of time.
RUN ln -s /usr/lib/python3/dist-packages/gi /opt/uv-tools/kaithem/lib/python3.13/site-packages/gi


# Create a group and user with UID/GID 1000
RUN addgroup -g 1000 devuser && \
    adduser -u 1000 -G vscode -D -s /bin/sh vscode

# (Optional) Set it as default for the image
USER vscode


ENTRYPOINT ["pw-jack", "kaithem"]