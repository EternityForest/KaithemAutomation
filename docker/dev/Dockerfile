ARG KAITHEM_VERSION
ARG KAITHEM_UID
ARG KAITHEM_GID
FROM kaithem-builder:${KAITHEM_VERSION:?error}


RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update

# Central management of the debian deps list
COPY ./KaithemAutomation/kaithem/data/debian_runtime_dependencies.sh \
    /workspace/debian_runtime_dependencies.sh

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    bash /workspace/debian_runtime_dependencies.sh


RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get install -y tzdata ca-certificates curl wget \
    iputils-ping make nano


# Try to fix mdns?
RUN sed -i 's/hosts:.*/hosts: files mdns4_minimal [NOTFOUND=return] dns mdns4/' /etc/nsswitch.conf



# The iceflow hack doesn't work with readonly images so
# Do it ahead of time.
RUN ln -s /usr/lib/python3/dist-packages/gi /opt/uv-tools/kaithem/lib/python3.13/site-packages/gi





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


RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get install -y mosquitto

# Dev specific stuff
RUN mkdir -p /root/.cache && \
    chown -R 1000:1000 /root/.cache


USER 1000:1000

WORKDIR /workspace/KaithemAutomation

#Debug in image: pw-jack uv run debugpy --listen 5178 /usr/local/bin/kaithem

CMD ["tail", "-f", "/dev/null"]