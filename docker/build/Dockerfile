# Docker multi staeg build that gets Rust and npm to compile the images
FROM debian:trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get install -y \
    curl \
    build-essential \
    make sudo git unzip rsync python3-venv

# Install Node
RUN curl -fsSL https://fnm.vercel.app/install | bash

RUN /root/.local/share/fnm/fnm install --lts

RUN echo 'eval "$(fnm env --use-on-cd)"' >> /root/.bashrc
ENV PATH="/root/.local/share/fnm/aliases/default/bin:$PATH"

RUN node -v && npx -v


# Install Rust and wasm32-unknown-unknown

RUN     --mount=type=cache,target=/root/.cargo \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Configure the environment path manually
ENV PATH="/root/.cargo/bin:${PATH}"

RUN --mount=type=cache,target=/root/.cargo \
    rustup target add wasm32-unknown-unknown



# Apt update only if we really have to
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    bash -c '[ -z "$(find /var/cache/apt/pkgcache.bin -mmin -1440 2>/dev/null)" ] && apt-get update'



RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get install -y \
    libasound2-dev libjack-jackd2-dev

RUN mkdir -p /app/debian/gits


# Most of this is just dowloading all the kaithem repos
WORKDIR /app/debian

RUN --mount=type=cache,target=/app/debian/gits,sharing=locked \
    [ -d /app/debian/gits/Dashbeard ] || git clone --depth 1 https://github.com/EternityForest/Dashbeard /app/debian/gits/Dashbeard


RUN --mount=type=cache,target=/app/debian/gits,sharing=locked \
    cd /app/debian/gits/Dashbeard && git fetch origin main && git reset --hard origin/main


RUN --mount=type=cache,target=/root/.npm \
    --mount=type=cache,target=/app/debian/gits,sharing=locked \
    cd /app/debian/gits/KaithemAutomation && npm ci


RUN --mount=type=cache,target=/root/.npm \
    --mount=type=cache,target=/app/debian/gits,sharing=locked \
    cd /app/debian/gits/Dashbeard && npm ci

ARG CACHE_BUST=1



RUN --mount=type=cache,target=/app/debian/gits,sharing=locked \
    --mount=type=bind,source=.,target=/tmp/KaithemAutomation \
    rsync -a --delete --filter=":- /tmp/KaithemAutomation/.gitignore" --exclude=".git/" /tmp/KaithemAutomation /app/debian/gits/KaithemAutomation


RUN --mount=type=cache,target=/app/debian/gits,sharing=locked \
    --mount=type=bind,source=.,target=/tmp/KaithemAutomation \
    ls -al /app/debian/gits/KaithemAutomation/


RUN --mount=type=cache,target=/app/debian/gits,sharing=locked \
    rm -rf /app/debian/gits/KaithemAutomation/.git

RUN --mount=type=cache,target=/app/debian/gits,sharing=locked \
    rm -rf /app/debian/gits/KaithemAutomation/.venv

# Actually build!

RUN --mount=type=cache,target=/app/debian/gits,sharing=locked \
    --mount=type=cache,target=/root/.npm \
    --mount=type=cache,target=/root/.cargo \
    --mount=type=cache,target=/app/target \
    --mount=type=cache,target=/root/.cache/uv \ 
    --mount=type=cache,target=/root/.local/share/uv \
    cd /app/debian/gits/KaithemAutomation && UV_LINK_MODE=copy uv sync && UV_LINK_MODE=copy make dev-build


ENV UV_TOOL_DIR=/opt/uv-tools
ENV UV_TOOL_BIN_DIR=/usr/local/bin

RUN --mount=type=cache,target=/app/debian/gits,sharing=locked \
    --mount=type=cache,target=/root/.local/share/uv \
    UV_LINK_MODE=copy uv tool install --verbose /app/debian/gits/KaithemAutomation