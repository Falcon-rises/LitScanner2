# worker.py
# Listens to Redis queue and runs tasks_impl.run_pipeline
import os
import time
import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get Redis URL from environment or fallback
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Queue and job key prefixes
JOB_QUEUE = "lithybrid:queue"
JOB_META_PREFIX = "lithybrid:job:"

# Import worker pipeline function
try:
    from tasks_impl import run_pipeline
except ImportError as e:
    print(f"ERROR: Cannot import run_pipeline: {e}")
    exit(1)

print("✅ Worker started. Listening for jobs...")

while True:
    try:
        res = redis_client.blpop(JOB_QUEUE, timeout=10)  # Wait up to 10s for a job
        if not res:
            continue

        _, project_id = res
        print(f"📦 Picked job: {project_id}")

        meta = redis_client.hgetall(JOB_META_PREFIX + project_id)
        if not meta:
            print(f"⚠️ No metadata found for job {project_id}")
            continue

        # Update status to "processing"
        redis_client.hset(JOB_META_PREFIX + project_id, mapping={
            "status": "processing",
            "progress": "2"
        })

        try:
            summary = run_pipeline(project_id, meta)
            num_papers = summary.get("num_papers", "unknown")
            print(f"✅ Pipeline finished for {project_id} -> {num_papers} papers")
            redis_client.hset(JOB_META_PREFIX + project_id, mapping={
                "status": "completed",
                "progress": "100",
                "num_papers": num_papers
            })

        except Exception as ex:
            print(f"❌ Pipeline error for {project_id}: {ex}")
            redis_client.hset(JOB_META_PREFIX + project_id, mapping={
                "status": "error",
                "progress": "0",
                "error": str(ex)
            })

    except Exception as e:
        print(f"🔥 Worker main loop error: {e}")
        time.sleep(2)  # Small delay before retrying
