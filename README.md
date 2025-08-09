# LitHybrid 2.0 — Clean Flat Scaffold

## Overview
LitHybrid converts a title → finds relevant research (OpenAlex) → stores metadata for ~thousands of papers → worker composes a long summary and stores results. Frontend provides progress, countdown, and APA export.

## Components
- `index.py` — FastAPI entry (deploy to Vercel)
- `worker.py` — long-running worker (run on Railway/Cloud Run/local)
- `tasks_impl.py` — pipeline implementation (worker-only)
- `app.py` — Streamlit frontend (runs locally or on Streamlit Cloud)
- `requirements.txt` — for Vercel API
- `worker-requirements.txt` — for worker host

## Quickstart (local)
1. Start Redis: `docker run -p 6379:6379 redis`
2. API (local): create venv & `pip install -r requirements.txt`, then `uvicorn index:app --reload --port 8000`
3. Worker: in another shell, install worker reqs `pip install -r worker-requirements.txt` then `python worker.py`
4. Frontend: `pip install streamlit` + `pip install -r worker-requirements.txt` if using same env, then `streamlit run app.py`

## Deploy
- Deploy `index.py` to Vercel (set `REDIS_URL` env in Vercel)
- Run the worker on a host with Redis and `worker-requirements.txt` installed
- Deploy Streamlit to Streamlit Cloud or run locally

## Notes
- This scaffold is production-minded and split to avoid Vercel cold-starts / heavy installs.
- For large exports (70k), implement object storage (S3) instead of storing the full JSON in Redis.
