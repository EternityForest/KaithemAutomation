# Docker multi stage build that gets Rust and npm to compile the images.

# This expects its build context to be set to a workspace folder which
# contains KaithemAutomation and Dashbeard.


FROM debian:trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update

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

RUN --mount=type=cache,target=/root/.cargo \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Configure the environment path manually
ENV PATH="/root/.cargo/bin:${PATH}"

RUN --mount=type=cache,target=/root/.cargo \
    rustup target add wasm32-unknown-unknown



# Apt update only if we really have to
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    bash -c '[ -z "$(find /var/cache/apt/pkgcache.bin -mmin -1440 2>/dev/null)" ] && apt-get update'

RUN mkdir -p /workspace

# Central management of the debian deps list
COPY ./KaithemAutomation/kaithem/data/debian_setup_dependencies.sh \
    /workspace/debian_setup_dependencies.sh

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    bash /workspace/debian_setup_dependencies.sh



# Actually build!

RUN --mount=type=cache,target=/root/.npm \
    --mount=type=cache,target=/root/.cargo \
    --mount=type=cache,target=/app/target \
    --mount=type=cache,target=/root/.cache/uv \ 
    --mount=type=cache,target=/root/.local/share/uv \
    --mount=type=bind,source=KaithemAutomation,target=/workspace/KaithemAutomation,rw  \
    --mount=type=bind,source=Dashbeard,target=/workspace/Dashbeard,rw  \
    --mount=type=cache,target=/workspace/KaithemAutomation/.venv \
    --mount=type=cache,target=/workspace/KaithemAutomation/__pycache__ \
    cd /workspace/KaithemAutomation && UV_LINK_MODE=copy uv sync
    
RUN --mount=type=cache,target=/root/.npm \
    --mount=type=cache,target=/root/.cargo \
    --mount=type=cache,target=/app/target \
    --mount=type=cache,target=/root/.cache/uv \ 
    --mount=type=cache,target=/root/.local/share/uv \
    --mount=type=bind,source=KaithemAutomation,target=/workspace/KaithemAutomation,rw  \
    --mount=type=bind,source=Dashbeard,target=/workspace/Dashbeard,rw \
    --mount=type=cache,target=/workspace/KaithemAutomation/.venv \
    --mount=type=cache,target=/workspace/KaithemAutomation/__pycache__ \
    --mount=type=cache,target=/workspace/KaithemAutomation/target \
    --mount=type=cache,target=/workspace/KaithemAutomation/dist \
    --mount=type=cache,target=/workspace/KaithemAutomation/wasm_kegs/__pycache__ \
    --mount=type=cache,target=/workspace/Dashbeard/.npm \
    --mount=type=cache,target=/workspace/Dashbeard/dist \
    cd /workspace/Dashbeard && npm install && npm run build ; \
    cd /workspace/KaithemAutomation && UV_LINK_MODE=copy make dev-build 


ENV UV_TOOL_DIR=/opt/uv-tools
ENV UV_TOOL_BIN_DIR=/usr/local/bin

RUN --mount=type=cache,target=/root/.local/share/uv \
    --mount=type=bind,source=KaithemAutomation,target=/workspace/KaithemAutomation,rw \
    --mount=type=bind,source=Dashbeard,target=/workspace/Dashbeard,rw \
    --mount=type=cache,target=/workspace/KaithemAutomation/.venv \
    --mount=type=cache,target=/workspace/KaithemAutomation/__pycache__ \
    --mount=type=cache,target=/workspace/KaithemAutomation/target \
    --mount=type=cache,target=/workspace/KaithemAutomation/dist \
    UV_LINK_MODE=copy uv tool install --verbose /workspace/KaithemAutomation