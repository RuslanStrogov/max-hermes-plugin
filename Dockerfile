FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HERMES_HOME=/root/.hermes \
    PYTHONPATH=/opt/max

WORKDIR /opt/max

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Runtime dependencies of the plugin
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Hermes Agent (gateway host for the plugin)
RUN pip install --no-cache-dir "hermes-agent>=0.19.0"

# Shared MAX API layer (imported as top-level `max_shared`)
COPY max_shared ./max_shared

# Native plugin, discoverable by Hermes at ~/.hermes/plugins/platforms/max
COPY plugins/platforms/max /root/.hermes/plugins/platforms/max

# Persistent config / sessions volume
VOLUME ["/root/.hermes"]

EXPOSE 8787

CMD ["hermes", "gateway", "run"]
