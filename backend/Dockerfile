FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY src ./src

RUN useradd --create-home --uid 10001 teachx \
    && mkdir -p /app/data \
    && chown -R teachx:teachx /app

USER teachx

ENV TEACHX_HOST=0.0.0.0 \
    TEACHX_PORT=8010 \
    TEACHX_DATABASE_PATH=/app/data/teachx.db \
    TEACHX_KNOWLEDGE_ROOT=/app/data/knowledge

EXPOSE 8010

HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3)"

CMD ["uvicorn", "teachx.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8010"]
