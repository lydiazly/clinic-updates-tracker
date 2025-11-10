# syntax=docker/dockerfile:1

# builder: Install dependencies using uv
# base: Prepare for runtime: copy python venv, add user
# run: Install browser and run script, change user
# user: Use another script to run user service
# test: no browser, root

ARG PYTHON_VERSION=3.12

# Build (temporary)
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS builder

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src/
RUN --mount=type=cache,target=/root/.cache/uv <<EOF
touch README.md
uv sync --frozen --no-dev --no-editable
uv pip install pytest-asyncio
EOF


# Prepare for runtime
FROM python:${PYTHON_VERSION}-slim-bookworm AS base

ARG UID=10001

ENV USERNAME=runner \
    PLAYWRIGHT_BROWSERS_PATH=/app/pw-browsers

# Update & install essential packages
#   curl, jq: for requesting Gmail access token
#   ca-certificates: for HTTPS requests (Gmail API, pip installs) (already installed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create a non-root user and sets ownership of /app
RUN <<EOF
useradd -lMU -u ${UID} ${USERNAME}
chown -R ${USERNAME}:${USERNAME} .
EOF

COPY --from=builder --chown=${USERNAME}:${USERNAME} /app/.venv .venv

ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=${USERNAME}:${USERNAME} . .

RUN chmod +x ./docker/docker-entrypoint*.sh


# Production runtime
FROM base AS run

# Install browser (chromium headless shell)
RUN python -m playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/*

USER ${USERNAME}

ENTRYPOINT ["/app/docker/docker-entrypoint.sh"]


# User service
FROM run AS user

ENTRYPOINT ["/app/docker/docker-entrypoint-user.sh"]


# Test environment
FROM base AS test

# Skip installing browser. Enter as root.

ENTRYPOINT ["/bin/bash"]
