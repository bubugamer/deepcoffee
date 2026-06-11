# DeepCoffee API

FastAPI backend for DeepCoffee.

## Local setup

```bash
cd deepcoffee-api
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

The API reads Markdown knowledge files from `../knowledge` by default.

## Useful local checks

```bash
pytest
curl http://127.0.0.1:8000/v1/health
curl http://127.0.0.1:8000/v1/knowledge/categories
```

For local authenticated requests without Supabase configured, use a development token:

```bash
curl -H "Authorization: Bearer dev:user-1:user@example.com" \
  http://127.0.0.1:8000/v1/me
```
