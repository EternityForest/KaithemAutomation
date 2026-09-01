ARG KAITHEM_VERSION
FROM kaithem-builder:${KAITHEM_VERSION:?error} as builder

# Stage 2: Final minimal runtime
FROM debian:trixie-slim

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get install -y \
    tz-data ca-certificates curl wget \
    iputils-ping make nano


# Ensure the wayland environment variables are exposed
ENV XDG_RUNTIME_DIR=/tmp/runtime-dir
ENV WAYLAND_DISPLAY=wayland-0


FROM debian:trixie


# Slow changing drivers
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y \
    mesa-va-drivers \
    libgl1-mesa-dri \
    libgl1 \
    libgles2 \
    libvulkan1 swayidle pipewire-audio-client-libraries wget

# chromium itself
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y \
    chromium \
    chromium-sandbox


COPY --from=builder /root/.local/bin/wayinhibit /usr/local/bin/wayinhibit

COPY ./KaithemAutomation/docker/kiosk/kiosk_run.sh /usr/local/bin/kiosk_run.sh

RUN chmod +x /usr/local/bin/kiosk_run.sh

ENTRYPOINT ["pw-jack", "wayinhibit", "--", "kiosk_run.sh"]

