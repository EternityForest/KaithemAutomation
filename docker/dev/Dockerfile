ARG KAITHEM_VERSION
FROM kaithem-builder:${KAITHEM_VERSION:?error}


# Central management of the debian deps list
COPY ./KaithemAutomation/kaithem/data/debian_runtime_dependencies.sh \
    /workspace/debian_runtime_dependencies.sh

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    bash /workspace/debian_runtime_dependencies.sh

ENV UV_TOOL_DIR=/opt/uv-tools
ENV UV_TOOL_BIN_DIR=/usr/local/bin

# UV_LINK_MODE=copy ensures packages are physically copied into the 
# image rather than hardlinked from the temporary cache mount.
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_LINK_MODE=copy uv tool install debugpy

WORKDIR /app/debian



# Copy the built and installed Kaithem files along with the UV venv
COPY --from=builder /opt/uv-tools/kaithem/ /opt/uv-tools/kaithem/
COPY --from=builder /usr/local/bin/kaithem /usr/local/bin/kaithem


# The iceflow hack doesn't work with readonly images so
# Do it ahead of time.
RUN ln -s /usr/lib/python3/dist-packages/gi /opt/uv-tools/kaithem/lib/python3.13/site-packages/gi

#Debug in image: pw-jack debugpy --listen 5178 /usr/local/bin/kaithem


ENTRYPOINT ["pw-jack", "kaithem"]