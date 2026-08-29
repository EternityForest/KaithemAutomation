ARG KAITHEM_VERSION
ARG KAITHEM_UID
ARG KAITHEM_GID
FROM kaithem-builder:${KAITHEM_VERSION:?error}


# Central management of the debian deps list
COPY ./KaithemAutomation/kaithem/data/debian_runtime_dependencies.sh \
    /workspace/debian_runtime_dependencies.sh

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    bash /workspace/debian_runtime_dependencies.sh

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get install -y direnv




# The iceflow hack doesn't work with readonly images so
# Do it ahead of time.
RUN ln -s /usr/lib/python3/dist-packages/gi /opt/uv-tools/kaithem/lib/python3.13/site-packages/gi


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

ENV UV_LINK_MODE=copy
ENV UV_CACHE_DIR=/workspace/uv_cache
USER 1000:1000

WORKDIR /workspace/KaithemAutomation



#Debug in image: pw-jack uv run debugpy --listen 5178 /usr/local/bin/kaithem



ENTRYPOINT ["pw-jack", "kaithem"]