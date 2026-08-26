FROM kaithem-build:dev as builder

FROM debian:trixie


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



WORKDIR /app/debian

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/


# Copy the built and installed Kaithem files along with the UV venv
COPY --from=builder /opt/uv-tools/kaithem/ /opt/uv-tools/kaithem/
COPY --from=builder /usr/local/bin/kaithem /usr/local/bin/kaithem


# The iceflow hack doesn't work with readonly images so
# Do it ahead of time.
RUN ln -s /usr/lib/python3/dist-packages/gi /opt/uv-tools/kaithem/lib/python3.13/site-packages/gi

# UV_LINK_MODE=copy ensures packages are physically copied into the 
# image rather than hardlinked from the temporary cache mount.
# RUN --mount=type=cache,target=/root/.cache/uv \
#     UV_LINK_MODE=copy make user-install-kaithem

ENTRYPOINT ["pw-jack", "kaithem"]