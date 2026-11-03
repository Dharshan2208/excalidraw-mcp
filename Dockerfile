FROM python:3.12-slim

# Prevent Python from writing bytecode and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user and home directory
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser

WORKDIR /app

# Copy project metadata and source code
COPY pyproject.toml README.md ./
COPY excalidraw_mcp ./excalidraw_mcp
COPY main.py ./

# Install package and dependencies
RUN pip install --no-cache-dir .

USER appuser

ENTRYPOINT ["exca-mcp"]
