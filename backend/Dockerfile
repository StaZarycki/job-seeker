FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --all-extras --no-install-project

COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --all-extras

# Personal files (config.toml, .env, cv/, data/, profile.overrides.toml) are not in the image:
# compose mounts them at /instance, and paths in the config are resolved relative to it.
ENV JOBSEEKER_CONFIG=/instance/config.toml
WORKDIR /instance

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["jobseeker", "serve", "--host", "0.0.0.0", "--port", "8000"]
