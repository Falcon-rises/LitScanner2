# api/worker_step.py
import os, json, time
from fastapi import FastAPI, Request
import httpx
import redis

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL must be set")

redis_client = redis.from_url(REDIS_URL, decode_responses=True)
JOB_PREFIX = os.getenv("JOB_PREFIX", "lithybrid:job:")
OPENALEX_WORKS = "https://api.openalex.org/works"

app = FastAPI()

def fetch_openalex_page(query, page=1, per_page=25):
    headers = {"User-Agent": "LitHybrid/1.0 (mailto:your-email@example.com)"}
    params = {"search": query, "per-page": per_page, "page": page}
    with httpx.Client(timeout=20, headers=headers) as client:
        r = client.get(OPENALEX_WORKS, params=params)
        r.raise_for_status()
        return r.json()

def normalize(p):
    ids = p.get("ids") or {}
    host = p.get("host_venue") or {}
    return {
        "id": p.get("id"),
        "title": p.get("title") or p.get("display_name"),
        "publication_year": p.get("publication_year") or p.get("year"),
        "authorships": p.get("authorships") or [],
        "doi": (ids.get("doi") if isinstance(ids, dict) else p.get("doi")) or "",
        "journal": (host.get("display_name") if isinstance(host, dict) else None) or p.get("venue") or "",
        "abstract": p.get("abstract") or "",
        "url": p.get("id") or p.get("url") or ""
    }

@app.post("/api/worker_step")
async def worker_step(request: Request):
    payload = {}
    try:
        body = await request.json()
        if isinstance(body, dict):
            payload = body
    except Exception:
        payload = {}

    project_id = payload.get("project_id")

    # gather candidates
    candidates = []
    if project_id:
        candidates = [project_id]
    else:
        # scan keys (small-scale acceptable); use SCAN for large scale later
        for key in redis_client.scan_iter(match=JOB_PREFIX + "*"):
            pid = key.replace(JOB_PREFIX, "")
            if ":" in pid:
                continue
            meta = redis_client.hgetall(JOB_PREFIX + pid)
            if not meta:
                continue
            if meta.get("status","") in ("queued", "discovering", "processing", "summarizing"):
                candidates.append(pid)

    processed = []
    for pid in candidates:
        key = JOB_PREFIX + pid
        meta = redis_client.hgetall(key)
        if not meta:
            continue

        status = meta.get("status", "queued")
        max_papers = int(meta.get("max_papers", 7000))
        per_run = int(meta.get("per_run", 100))
        offset = int(meta.get("next_offset", 0))

        papers_key = key + ":papers"
        processed_key = key + ":papers_processed"

        raw = redis_client.get(papers_key) or "[]"
        try:
            papers_list = json.loads(raw)
        except Exception:
            papers_list = []

        # Discovery step: append a small batch of raw results if papers_list is empty or incomplete
        if status == "queued" and len(papers_list) == 0:
            try:
                page = 1
                resp = fetch_openalex_page(meta.get("title",""), page=page, per_page=min(25, per_run))
                results = resp.get("results", [])
                for r in results:
                    papers_list.append(r)
                    if len(papers_list) >= max_papers:
                        break
                redis_client.set(papers_key, json.dumps(papers_list))
                redis_client.hset(key, mapping={"status":"discovering","progress":str(min(50, int((len(papers_list)/max_papers)*100)))})
            except Exception as e:
                redis_client.hset(key, mapping={"status":"discovering","progress":"0","error":str(e)})
                continue

        # Processing step: normalize the next chunk
        if len(papers_list) > 0:
            to_process = papers_list[offset: offset + per_run]
            normalized_chunk = []
            for raw_item in to_process:
                try:
                    normalized_chunk.append(normalize(raw_item))
                except Exception:
                    continue

            existing_raw = redis_client.get(processed_key) or "[]"
            try:
                existing = json.loads(existing_raw)
            except Exception:
                existing = []
            existing.extend(normalized_chunk)
            redis_client.set(processed_key, json.dumps(existing))

            new_offset = offset + len(to_process)
            progress = int((new_offset / max(1, max_papers)) * 100)
            redis_client.hset(key, mapping={"next_offset": str(new_offset), "progress": str(min(progress, 99)), "status": "processing"})

            # completion condition
            if new_offset >= max_papers or new_offset >= len(papers_list):
                # produce a cheap extractive summary
                snippets = []
                for rec in existing:
                    a = rec.get("abstract","") or ""
                    if a:
                        s = a.split(".")
                        snippet = ".".join(s[:2]).strip()
                        if snippet:
                            snippets.append(snippet + ".")
                compose = "Automatic reduce summary for: " + meta.get("title","") + "\n\n"
                compose += "Collected {} processed records.\n\n".format(len(existing))
                compose += "Representative snippets:\n"
                for s in snippets[:20]:
                    compose += "- " + s.replace("\n"," ")[:400] + "\n"

                redis_client.hset(key, mapping={"summary": json.dumps({"title": meta.get("title"), "num_papers": len(existing), "composed_summary": compose}), "status":"done", "progress":"100"})
                redis_client.set(papers_key, json.dumps(existing))
            processed.append(pid)

    return {"processed": processed, "count": len(processed)}

