import os
import json
import redis
from tasks_impl import run_pipeline
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

JOB_META_PREFIX = "lithybrid:job:"

def handler(request, response):
    try:
        project_id = request.args.get("project_id")
        if not project_id:
            return response.status(400).json({"error": "project_id required"})

        meta = redis_client.hgetall(JOB_META_PREFIX + project_id)
        if not meta:
            return response.status(404).json({"error": "No metadata found"})

        redis_client.hset(JOB_META_PREFIX + project_id, mapping={"status": "processing", "progress": "2"})

        summary = run_pipeline(project_id, meta)

        redis_client.hset(JOB_META_PREFIX + project_id, mapping={
            "status": "done",
            "progress": "100",
            "summary": json.dumps(summary)
        })

        return response.status(200).json({"success": True, "summary": summary})

    except Exception as e:
        return response.status(500).json({"error": str(e)})
