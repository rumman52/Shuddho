FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY services ./services
COPY shared ./shared
COPY ml ./ml
COPY data ./data

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

CMD ["sh", "-c", "python -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
