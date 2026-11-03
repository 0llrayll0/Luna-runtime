FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY luna ./luna
RUN pip install --upgrade pip && pip install -e .

# Runtime state lives in /data/.luna (mounted volume).
ENV LUNA_CONFIG=/data/.luna/config.yaml

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)" || exit 1

CMD ["uvicorn", "luna.api.server:app", "--host", "0.0.0.0", "--port", "8000"]