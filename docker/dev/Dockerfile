ARG KAITHEM_VERSION
ARG KAITHEM_UID
ARG KAITHEM_GID

FROM --platform=${BUILDPLATFORM} kaithem-builder AS builder

ARG TARGETARCH


RUN --mount=type=cache,id=apt-cache-${TARGETARCH},target=/var/cache/apt,sharing=private \
    --mount=type=cache,id=apt-lists-${TARGETARCH},target=/var/lib/apt/lists,sharing=private \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update

# Central management of the debian deps list
COPY ./KaithemAutomation/kaithem/data/debian_runtime_dependencies.sh \
    /workspace/debian_runtime_dependencies.sh

RUN --mount=type=cache,id=apt-cache-${TARGETARCH},target=/var/cache/apt,sharing=private \
    --mount=type=cache,id=apt-lists-${TARGETARCH},target=/var/lib/apt/lists,sharing=private \
    bash /workspace/debian_runtime_dependencies.sh


RUN --mount=type=cache,id=apt-cache-${TARGETARCH},target=/var/cache/apt,sharing=private \
    --mount=type=cache,id=apt-lists-${TARGETARCH},target=/var/lib/apt/lists,sharing=private \
    apt-get install -y tzdata ca-certificates curl wget \
    iputils-ping make nano


# Try to fix mdns?
RUN sed -i 's/hosts:.*/hosts: files mdns4_minimal [NOTFOUND=return] dns mdns4/' /etc/nsswitch.conf



RUN mkdir -p /app-home ; \
    chown -R 1000:1000 /app-home ; 

ENV HOME=/app-home

RUN mkdir -p /workspace/KaithemAutomation/.venv; \
    mkdir -p /workspace/KaithemAutomation/.test_venvs; \
    mkdir -p /workspace/KaithemAutomation/__pycache__; \
    mkdir -p /workspace/Dashbeard/ ; \    
    mkdir -p /workspace/Dashbeard/.npm; \
    mkdir -p /workspace/Dashbeard/dist; \
    mkdir -p /workspace/KaithemAutomation/wasm_kegs/__pycache__ ;\
    mkdir -p /workspace/KaithemAutomation/target ;\
    mkdir -p /workspace/KaithemAutomation/dist ; \
    mkdir -p /workspace/uv_cache ; \
    chown -R 1000:1000 /workspace/ ; 


RUN --mount=type=cache,id=apt-cache-${TARGETARCH},target=/var/cache/apt,sharing=private \
    --mount=type=cache,id=apt-lists-${TARGETARCH},target=/var/lib/apt/lists,sharing=private \
    apt-get install -y mosquitto

# Dev specific stuff
RUN mkdir -p /root/.cache && \
    chown -R 1000:1000 /root/.cache

RUN mkdir -p /app-home/.cache && \
    chown -R 1000:1000 /app-home

USER 1000:1000

WORKDIR /workspace/KaithemAutomation

#Debug in image: pw-jack uv run debugpy --listen 5178 /usr/local/bin/kaithem

CMD ["tail", "-f", "/dev/null"]