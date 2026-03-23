FROM python:3.10-slim

LABEL maintainer="BespokeAgile"
LABEL description="BespokeAgile Comply -- open-source compliance gap analysis for any codebase"

WORKDIR /app

# Install git (needed for cloning repos during scans)
RUN apt-get update && apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

# Copy the whole comply package (pyproject.toml is inside this directory)
COPY . ./

# Install the package
RUN pip install --no-cache-dir .

# Self-hosted mode (not demo)
ENV COMPLY_DEMO_MODE=false

# Persist scan history and config
VOLUME /root/.comply

# Dashboard port
EXPOSE 8001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run the server (bind to all interfaces for container networking)
CMD ["bespoke-comply", "serve", "--host", "0.0.0.0", "--port", "8001"]
