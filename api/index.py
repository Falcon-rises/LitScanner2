# api/index.py
import os
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import redis
import traceback

app = FastAPI()

def get_redis():
    """Connect to Redis using env variable or raise a clear error."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL environment variable is missing.")
    try:
        return redis.from_url(redis_url)
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Redis: {e}")

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """Check the status of a given job."""
    try:
        r = get_redis()
        status = r.get(f"job:{job_id}:status")
        if status is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"job_id": job_id, "status": status.decode("utf-8")}
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "trace": traceback.format_exc()}
        )

@app.post("/api/run_job")
async def run_job(request: Request):
    """
    Trigger a job without blocking the request.
    Vercel functions must return in <10s, so heavy work should be done elsewhere.
    """
    try:
        data = await request.json()
        job_id = data.get("job_id")
        if not job_id:
            raise HTTPException(status_code=400, detail="Missing job_id")

        # Import heavy modules here (lazy import)
        import tasks_impl

        # Mark job as started
        r = get_redis()
        r.set(f"job:{job_id}:status", "started")

        # Run the pipeline (⚠️ will still block if it takes >10s)
        # For production: push this to a worker queue instead
        result = tasks_impl.run_pipeline(data)

        # Store result in Redis
        r.set(f"job:{job_id}:status", "completed")
        r.set(f"job:{job_id}:result", json.dumps(result, default=str))

        return {"job_id": job_id, "status": "completed", "result": result}

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "trace": traceback.format_exc()}
        )

@app.get("/api/result/{job_id}")
async def get_result(job_id: str):
    """Retrieve the result of a completed job."""
    try:
        r = get_redis()
        result = r.get(f"job:{job_id}:result")
        if result is None:
            raise HTTPException(status_code=404, detail="Result not found")
        return json.loads(result)
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "trace": traceback.format_exc()}
        )
