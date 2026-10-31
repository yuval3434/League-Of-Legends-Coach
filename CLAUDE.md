# LoL Coach

Personal League of Legends coach. Pulls match data from the Riot API,
computes stats in SQL, and uses an LLM agent with tools to explain
them in plain language.

## Stack
Python 3.12 · FastAPI · PostgreSQL · ChromaDB · Gradio · Docker

## Structure
- `ingestion/`  Riot API client, rate limiting, storage
- `analytics/`  stat functions — each one becomes an agent tool
- `rag/`        document loading, chunking, embedding, search
- `agent/`      LLM agent, tool definitions, system prompt
- `eval/`       evaluation questions and scoring
- `ui/`         Gradio app

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
