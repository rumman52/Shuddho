FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SHUDDHO_CORRECTOR_ENABLED=auto \
    SHUDDHO_DETECTOR_ENABLED=auto

WORKDIR /app

COPY pyproject.toml README.md ./
COPY services ./services
COPY shared ./shared
COPY ml ./ml
COPY data/runtime ./data/runtime
COPY artifacts/detector ./artifacts/detector
COPY artifacts/corrector/corrector-base/metadata.json ./artifacts/corrector/corrector-base/metadata.json
COPY artifacts/corrector/corrector-base/metrics.json ./artifacts/corrector/corrector-base/metrics.json

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()" || exit 1

CMD ["sh", "-c", "python -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
