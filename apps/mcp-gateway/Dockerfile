# Secure MCP Gateway — gateway API image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/packages:/app/apps/mcp-gateway

WORKDIR /app

# Install dependencies first for layer caching.
COPY pyproject.toml /app/pyproject.toml
COPY packages /app/packages
RUN pip install --no-cache-dir -e .

# Application code
COPY apps/mcp-gateway /app/apps/mcp-gateway

EXPOSE 8000

# Non-root runtime user
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/apps/mcp-gateway"]
