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
    mkdir -p /workspace/KaithemAutomation/.venv311; \
    mkdir -p /workspace/KaithemAutomation/.venv312; \
    mkdir -p /workspace/KaithemAutomation/.venv313; \
    mkdir -p /workspace/KaithemAutomation/.venv_clean_no_dev; \
    mkdir -p /workspace/KaithemAutomation/__pycache__; \
    mkdir -p /workspace/Dashbeard/ ; \
    chown 1000:1000 /workspace/*

USER 1000:1000

WORKDIR /workspace/KaithemAutomation



#Debug in image: cd


ENTRYPOINT ["pw-jack", "kaithem"]