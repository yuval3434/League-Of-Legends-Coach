# LoL Coach

Personal League of Legends coach. Pulls match data from the Riot API,
computes stats in SQL, compares them with benchmark cohorts of other
players, and uses an LLM agent with tools to explain them in plain
language.

## Stack
- Backend: Python 3.12 · FastAPI · PostgreSQL · Alembic · Docker
- Web app: React · TypeScript · Vite · Tailwind · Recharts
- Coach: Claude models, or a local model through Ollama

## Structure
- `ingestion/`  Riot API client, rate limiting, storage, players, keys
- `analytics/`  stat functions — each one becomes an agent tool
- `benchmarks/` cohort pulls and comparisons against them
- `agent/`      LLM agent, tool definitions, system prompt, number check, citations
- `eval/`       evaluation questions, code checks and the model grader
- `demo/`       anonymized demo dataset: export and load
- `web/`        React web app (the UI)
- `ui/`         older Gradio app, kept working
- `alembic/`    database migrations
- `scripts/`    backups and one-off checks
- `main.py`     the FastAPI app

## Rules
- The LLM never computes a number. Every number comes from a tool.
- Every stat returns its sample size. Fewer than 10 games → say so.
- Every Riot API call goes through the rate limiter.
- Store raw API responses next to parsed data.
- Secrets only in `.env`, never committed.

## Working agreement
I'm a CS student building this to learn LLM engineering and to talk
about it in interviews. Explain decisions before writing code, give me
options with trade-offs when there's a real choice, and keep changes
small enough that I can read them.
