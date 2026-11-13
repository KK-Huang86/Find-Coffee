FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

ARG ENV=dev

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project $(if [ "$ENV" = "prod" ]; then echo "--no-dev"; fi)

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked $(if [ "$ENV" = "prod" ]; then echo "--no-dev"; fi)

ENV PATH="/app/.venv/bin:$PATH"

# 建置期收集 static 檔供 WhiteNoise serve；放在 /app 之外，docker compose 掛載 .:/app 時才不會被蓋掉
# settings 載入時需要這些變數，僅給佔位值，不連線資料庫
ENV STATIC_ROOT=/opt/staticfiles
RUN SECRET_KEY=collectstatic-placeholder \
    DB_ENGINE=django.db.backends.sqlite3 DB_NAME=unused DB_USER= DB_PASSWORD= DB_HOST= \
    python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", "--worker-tmp-dir", "/dev/shm"]
