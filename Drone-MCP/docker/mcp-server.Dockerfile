FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV DRONE_MCP_REPO_ROOT=/workspace/repo

WORKDIR /workspace/repo

COPY requirements-mcp.txt /tmp/requirements-mcp.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    docker-cli \
    gosu \
    && rm -rf /var/lib/apt/lists/*

COPY . /workspace/repo
COPY docker/mcp-entrypoint.sh /usr/local/bin/mcp-entrypoint.sh

RUN pip install --no-cache-dir -r /tmp/requirements-mcp.txt && \
    pip install --no-cache-dir /workspace/repo && \
    useradd -m -u 1000 mcpuser && \
    chmod +x /usr/local/bin/mcp-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/mcp-entrypoint.sh"]
CMD ["python", "/workspace/repo/drone_runtime_server.py"]
