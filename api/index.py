# api/index.py
import os
import json
import uuid
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# Lazy import Redis to avoid Vercel cold-start crashes if REDIS_URL missing
import redis

# Environment variables
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL must be set in environment variables")

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
except Exception as e:
    raise RuntimeError(f"Failed to connect to Redis: {e}")

JOB_PREFIX = os.getenv("JOB_PREFIX", "lithybrid:job:")

app = FastAPI(title="LitHybrid API (chunked-worker)")


# -------- Models -------- #
class ProjectRequest(BaseModel):
    title: str
    max_papers: Optional[int] = 7000
    per_run: Optional[int] = 100
    expected_time_minutes: Optional[int] = 30


# -------- Routes -------- #
@app.get("/")
def root():
    return {"ok": True, "service": "LitHybrid API (chunked-worker)"}


@app.post("/api/projects")
def create_project(req: ProjectRequest):
    project_id = str(uuid.uuid4())
    meta = {
        "project_id": project_id,
        "title": req.title,
        "max_papers": str(req.max_papers),
        "per_run": str(req.per_run),
        "status": "queued",
        "progress": "0",
        "next_offset": "0",
        "expected_time_minutes": str(req.expected_time_minutes or 30)
    }
    redis_client.hset(JOB_PREFIX + project_id, mapping=meta)
    redis_client.set(JOB_PREFIX + project_id + ":papers", json.dumps([]))
    return {
        "project_id": project_id,
        "status": "queued",
        "expected_time_minutes": meta["expected_time_minutes"]
    }


@app.post("/api/run_job")
def run_job(project_id: str = Query(...)):
    meta = redis_client.hgetall(JOB_PREFIX + project_id)
    if not meta:
        raise HTTPException(status_code=404, detail="No metadata found")

    redis_client.hset(JOB_PREFIX + project_id, mapping={
        "status": "processing",
        "progress": "2"
    })

    try:
        # Heavy import inside function
        from tasks_impl import run_pipeline
        summary = run_pipeline(project_id, meta)

        redis_client.hset(JOB_PREFIX + project_id, mapping={
            "status": "done",
            "progress": "100",
            "summary": json.dumps(summary)
        })

        return {"success": True, "summary": summary}
    except Exception as e:
        redis_client.hset(JOB_PREFIX + project_id, mapping={
            "status": "error",
            "progress": "0",
            "error": str(e)
        })
        # Log for Vercel dashboard
        print(f"[ERROR] run_job failed for {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}/status")
def project_status(project_id: str):
    key = JOB_PREFIX + project_id
    if not redis_client.exists(key):
        raise HTTPException(status_code=404, detail="project not found")
    data = redis_client.hgetall(key)
    for k in ("max_papers", "per_run", "next_offset"):
        if k in data:
            try:
                data[k] = int(data[k])
            except Exception:
                pass
    return data


@app.get("/api/projects/{project_id}/papers")
def project_papers(project_id: str, page: int = 1, per_page: int = 1000):
    papers_key = JOB_PREFIX + project_id + ":papers"
    if not redis_client.exists(papers_key):
        raise HTTPException(status_code=404, detail="papers not available")
    raw = redis_client.get(papers_key) or "[]"
    try:
        papers = json.loads(raw)
    except Exception:
        papers = []
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "project_id": project_id,
        "page": page,
        "per_page": per_page,
        "total": len(papers),
        "papers": papers[start:end]
    }


@app.get("/api/projects/{project_id}/summary")
def project_summary(project_id: str):
    key = JOB_PREFIX + project_id
    if not redis_client.exists(key):
        raise HTTPException(status_code=404, detail="project not found")
    summary_raw = redis_client.hget(key, "summary")
    if not summary_raw:
        raise HTTPException(status_code=404, detail="summary not ready")
    try:
        return {"project_id": project_id, "summary": json.loads(summary_raw)}
    except Exception:
        return {"project_id": project_id, "summary": summary_raw}
