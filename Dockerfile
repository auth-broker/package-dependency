FROM python:3.12.7-slim

# 1) tools needed for git deps
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates bash \
 && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Configure ENV
ENV PYTHONBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Directory for package
WORKDIR /package

# Install project dependencies (ensures cache before project change)
COPY pyproject.toml tox.ini README.md .

# Inject a temporary .netrc from a build secret and run uv
RUN --mount=type=secret,id=github_token,target=/run/secrets/github_token,required \
    bash -eu -o pipefail -c ' \
      GITHUB_LOGIN="${GITHUB_USER:-oauth2}"; \
      TOKEN="$(cat /run/secrets/github_token)"; \
      printf "machine github.com\n  login %s\n  password %s\n" "$GITHUB_LOGIN" "$TOKEN" > /root/.netrc; \
      chmod 600 /root/.netrc; \
      uv sync --no-install-project \
    '

# Install remaining project
COPY src ./src
COPY tests ./tests
RUN uv sync
