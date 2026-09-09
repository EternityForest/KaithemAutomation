FROM kaithem-native-rust-builder AS builder

# Stage 2: Final minimal runtime
FROM debian:trixie-slim

ARG KAITHEM_VERSION
ARG TARGETARCH


RUN rm -f /etc/apt/apt.conf.d/docker-clean; \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache
   
RUN --mount=type=cache,id=apt-cache-${TARGETARCH},target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lists-${TARGETARCH},target=/var/lib/apt/lists,sharing=locked \
    apt-get update

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive


COPY ./KaithemAutomation/kaithem/data/debian_core_utils.sh \
    /workspace/debian_core_utils.sh

RUN --mount=type=cache,id=apt-cache-${TARGETARCH},target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lists-${TARGETARCH},target=/var/lib/apt/lists,sharing=locked \
    bash /workspace/debian_core_utils.sh


# Ensure the wayland environment variables are exposed
ENV XDG_RUNTIME_DIR=/tmp/runtime-dir
ENV WAYLAND_DISPLAY=wayland-0





# Slow changing drivers
RUN --mount=type=cache,id=apt-cache-${TARGETARCH},target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lists-${TARGETARCH},target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-get install -y \
    mesa-va-drivers \
    libgl1-mesa-dri \
    libgl1 \
    libgles2 \
    libvulkan1 swayidle pipewire-audio-client-libraries wget

# chromium itself
RUN --mount=type=cache,id=apt-cache-${TARGETARCH},target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lists-${TARGETARCH},target=/var/lib/apt/lists,sharing=locked \
    apt-get install -y \
    chromium \
    chromium-sandbox




COPY --from=builder /usr/local/cargo/bin/wayinhibit /usr/local/bin/wayinhibit

COPY ./KaithemAutomation/docker/kiosk/kiosk_run.sh /usr/local/bin/kiosk_run.sh

RUN chmod +x /usr/local/bin/kiosk_run.sh

ENTRYPOINT ["pw-jack", "wayinhibit", "--", "kiosk_run.sh"]

