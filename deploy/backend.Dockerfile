FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEEPCOFFEE_KNOWLEDGE_DIR=/knowledge

WORKDIR /app

COPY deepcoffee-api/pyproject.toml deepcoffee-api/README.md ./
COPY deepcoffee-api/app ./app
COPY knowledge /knowledge

RUN pip install --no-cache-dir ".[observability]"

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
