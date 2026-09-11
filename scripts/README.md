# Helper scripts

These are mostly meant to run from the makefile in the root and assume the project root as cwd.
Go to the root and do "make help" for more info.

The exception is `render-compose-override.sh`, which is also designed to run
directly. It regenerates `docker/docker-compose.override.yaml` so that the
host's audio/video/etc. group GIDs are inlined as a proper YAML list. Use it
on its own before invoking `docker compose`:

    scripts/render-compose-override.sh
    COMPOSE_FILE=docker/docker-compose.yaml:docker/docker-compose.override.yaml \
        docker compose up -d