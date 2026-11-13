FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend \
    DATA_DIR=/app/data

WORKDIR /app

COPY backend/requirements.lock.txt ./
RUN python -m pip install --only-binary=:all: -r requirements.lock.txt

RUN groupadd --gid 10001 stadium \
    && useradd --uid 10001 --gid stadium --no-create-home stadium \
    && mkdir -p /app/data \
    && chown stadium:stadium /app/data

COPY backend/app ./backend/app
COPY frontend ./frontend
COPY scripts ./scripts

USER stadium
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
