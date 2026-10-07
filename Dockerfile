FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BISNU_HOST=0.0.0.0 \
    BISNU_PORT=8080 \
    LOG_LEVEL=info \
    BISNU_REQUIRE_PERSISTENT_DB=true \
    LLM_GATEWAY_ENABLED=true \
    QWEN_ENABLED=false \
    LLAMA_ENABLED=false \
    BISNU_ENABLED=false \
    ENSEMBLE_ENABLED=false \
    VERIFIER_ENABLED=false \
    SYNTHESIS_ENABLED=false

WORKDIR /app

COPY requirements-backend.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements-backend.txt

COPY bisnu_x ./bisnu_x
COPY run_web.py ./run_web.py

RUN useradd --uid 10001 --create-home bisnu \
    && chown -R bisnu:bisnu /app

USER bisnu

CMD ["sh", "-c", "uvicorn bisnu_x.app:app --host 0.0.0.0 --port ${PORT:-8080} --log-level ${LOG_LEVEL:-info} --access-log"]
