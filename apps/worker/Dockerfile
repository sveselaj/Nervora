# Secure MCP Gateway — async worker image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/packages:/app/apps/worker

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY packages /app/packages
RUN pip install --no-cache-dir -e .

COPY apps/worker /app/apps/worker

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

CMD ["python", "/app/apps/worker/worker.py"]
