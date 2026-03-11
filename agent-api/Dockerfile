FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Application code
COPY src/ src/
COPY skills/ skills/

# Create workspace and data directories
RUN mkdir -p workspace data

# Non-root user
RUN useradd -r -s /bin/false agentuser \
    && chown -R agentuser:agentuser /app
USER agentuser

EXPOSE 8000

CMD ["uvicorn", "agent_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
