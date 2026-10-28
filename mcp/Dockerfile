# MCP server image (streamable HTTP on :8000/mcp). Build: docker build -t sjrwmd-mcp:dev mcp/
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[postgis]"
USER 10001
ENV SJRWMD_MCP_TRANSPORT=streamable-http SJRWMD_MCP_HOST=0.0.0.0 SJRWMD_MCP_PORT=8000 HOME=/tmp
EXPOSE 8000
ENTRYPOINT ["sjrwmd-mcp"]
