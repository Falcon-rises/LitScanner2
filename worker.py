# worker.py
import os
import time
import json
import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JOB_QUEUE = os.getenv("JOB_QUEUE", "lithybrid:queue")
JOB_META_PREFIX = os.getenv("JOB_META_PREFIX", "lithybrid:job:")

# Connect to Redis
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    print(f"[Worker] Connected to Redis at {REDIS_URL}")
except Exception as e:
    print(f"[Worker] Failed to connect to Redis: {e}")
    raise

# Import the pipeline function
try:
    from tasks_impl import run_pipeline
except ImportError:
    print("[Worker] tasks_impl.py not found — cannot import run_pipeline()")
    raise

print("[Worker] Listening for jobs on queue:", JOB_QUEUE)

def process_job(project_id, meta):
    """Process a single job from the queue."""
    try:
        redis_client.hset(JOB_META_PREFIX + project_id, mapping={
            "status": "processing",
            "progress": "2"
        })

        summary = run_pipeline(project_id, meta)
        redis_client.hset(JOB_META_PREFIX + project_id, mapping={
            "status": "completed",
            "progress": "100",
            "result": json.dumps(summary)
        })
        print(f"[Worker] Job {project_id} completed successfully")
    except Exception as ex:
        redis_client.hset(JOB_META_PREFIX + project_id, mapping={
            "status": "error",
            "progress": "0",
            "error": str(ex)
        })
        print(f"[Worker] Error processing job {project_id}: {ex}")

while True:
    try:
        res = redis_client.blpop(JOB_QUEUE, timeout=10)
        if not res:
            continue

        _, project_id = res
        print(f"[Worker] Picked job: {project_id}")

        meta = redis_client.hgetall(JOB_META_PREFIX + project_id)
        if not meta:
            print(f"[Worker] No metadata found for job {project_id}")
            continue

        process_job(project_id, meta)

    except Exception as e:
        print(f"[Worker] Main loop error: {e}")
        time.sleep(2)

