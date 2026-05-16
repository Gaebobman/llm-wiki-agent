FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    file \
    git \
    jq \
    poppler-utils \
    ripgrep \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-kor \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY agent /app/agent
COPY scripts /app/scripts
COPY vendor /app/vendor

RUN pip install --upgrade pip && \
    pip install uv && \
    uv pip install --system -e .

RUN chmod +x /app/scripts/*.sh

CMD ["python", "-m", "agent.main"]
