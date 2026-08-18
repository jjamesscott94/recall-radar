FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY recall_radar ./recall_radar
COPY data ./data

RUN pip install --no-cache-dir .

# Default to the hosted HTTP transport; override with RECALL_RADAR_TRANSPORT=stdio
ENV RECALL_RADAR_TRANSPORT=streamable-http \
    RECALL_RADAR_HOST=0.0.0.0 \
    RECALL_RADAR_PORT=8000

EXPOSE 8000

CMD ["recall-radar-server"]
