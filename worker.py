# worker.py
# Simple worker: BLPOP Redis queue and run tasks_impl.run_pipeline
import os
import time
import json
import redis
from dotenv import load_dotenv

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

JOB_QUEUE = "lithybrid:queue"
JOB_META_PREFIX = "lithybrid:job:"

# import worker pipeline implementation
from tasks_impl import run_pipeline

print("Worker started. Listening for jobs...")

while True:
    try:
        res = redis_client.blpop(JOB_QUEUE, timeout=10)
        if not res:
            continue
        _, project_id = res
        print("Picked job:", project_id)
        meta = redis_client.hgetall(JOB_META_PREFIX + project_id)
        if not meta:
            print("No metadata for", project_id)
            continue
        redis_client.hset(JOB_META_PREFIX + project_id, mapping={"status": "processing", "progress": "2"})
        try:
            summary = run_pipeline(project_id, meta)
            print("Pipeline finished for", project_id, "->", summary.get("num_papers"))
        except Exception as ex:
            print("Pipeline error:", ex)
            redis_client.hset(JOB_META_PREFIX + project_id, mapping={"status": "error", "progress": "0", "error": str(ex)})
    except Exception as e:
        print("Worker main loop error:", e)
        time.sleep(2)
