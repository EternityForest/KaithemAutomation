ARG BUILDPLATFORM

FROM --platform=${BUILDPLATFORM} kaithem-builder AS builder

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

# Central management of the debian deps list
COPY ./KaithemAutomation/kaithem/data/debian_runtime_dependencies.sh \
    /workspace/debian_runtime_dependencies.sh

RUN --mount=type=cache,id=apt-cache-${TARGETARCH},target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lists-${TARGETARCH},target=/var/lib/apt/lists,sharing=locked \
    bash /workspace/debian_runtime_dependencies.sh

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_TOOL_DIR=/opt/uv-tools
ENV UV_TOOL_BIN_DIR=/usr/local/bin

# UV_LINK_MODE=copy ensures packages are physically copied into the 
# image rather than hardlinked from the temporary cache mount.
RUN --mount=type=cache,id=uv-cache-${TARGETARCH},target=/root/.cache/uv \
    UV_LINK_MODE=copy uv tool install debugpy


RUN mkdir -p /app-home ; \
    mkdir -p /app-home/.cache/sherpa-onnx-models ; \
    chown -R 1000:1000 /app-home ; 

ENV HOME=/app-home

# Copy the built and installed Kaithem files along with the UV venv
COPY --from=builder /opt/uv-tools/kaithem/ /opt/uv-tools/kaithem/
COPY --from=builder /usr/local/bin/kaithem /usr/local/bin/kaithem


# The iceflow hack doesn't work with readonly images so
# Do it ahead of time.
RUN ln -s /usr/lib/python3/dist-packages/gi /opt/uv-tools/kaithem/lib/python3.13/site-packages/gi



ENTRYPOINT ["pw-jack", "kaithem"]