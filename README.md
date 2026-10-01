# TeachX

TeachX is a web-first AI tutoring platform. It keeps the parts of DeepTutor
that matter most for learning products:

- a streaming agent loop
- model tool calling
- reusable tutoring capabilities
- knowledge-grounded answers
- durable conversations
- a polished Next.js interface

The first milestone uses a mock model so the complete product path can run
without an API key. Real OpenAI-compatible providers are configured through
environment variables.

## Repository layout

```text
frontend/   Next.js 16 + React 19 web application
backend/    FastAPI service and TeachX agent runtime
docs/       Architecture and engineering notes
data/       Local runtime data (ignored by Git)
```

## Local development

### Backend

```bash
cd backend
uv sync
uv run uvicorn teachx.main:app --app-dir src --reload --port 8010
```

### Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000.

## Model configuration

The default provider is `mock`, which makes local development deterministic.
To use an OpenAI-compatible endpoint:

```bash
export TEACHX_LLM_PROVIDER=openai
export TEACHX_MODEL=gpt-4.1-mini
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=...
```

## Status

This repository is under active construction. The current milestone focuses
on a chat vertical slice and the protocol required by the reused frontend.
