FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# One worker on purpose: the rate limiter lives in this process's memory,
# so a second worker would have its own count and could exceed Riot's limit.
CMD ["sh", "-c", "uv run --no-dev alembic upgrade head && uv run --no-dev uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1"]
