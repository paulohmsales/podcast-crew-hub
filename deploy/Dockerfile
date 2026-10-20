FROM python:3.13-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock .python-version ./
RUN pip install --no-cache-dir uv==0.11.18 && uv sync --frozen --no-dev
COPY . .
# Migrations run on every start; SQLite lives on the /data volume.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
