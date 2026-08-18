FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY recall_radar ./recall_radar
COPY data ./data

RUN pip install --no-cache-dir .

# Default to the hosted HTTP transport; override with RECALL_RADAR_TRANSPORT=stdio
# NOTE: do NOT set RECALL_RADAR_PORT here — Cloud Run injects PORT=8080 and the
# server honors it (see config.py). Setting a fixed port breaks the health check.
ENV RECALL_RADAR_TRANSPORT=streamable-http \
    RECALL_RADAR_HOST=0.0.0.0

EXPOSE 8080

CMD ["recall-radar-server"]
