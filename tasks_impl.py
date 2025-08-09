# tasks_impl.py
# Worker-only pipeline implementation.
# Keeps network calls robust, stores paper metadata to Redis for frontend to fetch.
import os
import time
import json
import httpx
from typing import Dict, Any, List
import redis
from dotenv import load_dotenv

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

OPENALEX_WORKS = "https://api.openalex.org/works"
MAX_PER_PAGE = int(os.getenv("MAX_PER_PAGE", "25"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "100"))  # worker can increase; API rate limits apply

JOB_META_PREFIX = "lithybrid:job:"
JOB_PAPERS_SUFFIX = ":papers"

def discover_papers_openalex(query: str, limit: int = 200) -> List[Dict[str, Any]]:
    collected = []
    page = 1
    per_page = min(MAX_PER_PAGE, 25)
    headers = {"User-Agent": "LitHybrid/1.0 (mailto:your-email@example.com)"}
    while len(collected) < limit and page <= MAX_PAGES:
        params = {"search": query, "per-page": per_page, "page": page}
        try:
            with httpx.Client(timeout=30, headers=headers) as client:
                resp = client.get(OPENALEX_WORKS, params=params)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results") or []
                if not results:
                    break
                collected.extend(results)
        except Exception as e:
            print("OpenAlex fetch error:", e)
            break
        page += 1
        time.sleep(0.15)
    return collected[:limit]

def normalize_record(p: Dict[str, Any]) -> Dict[str, Any]:
    rec = {}
    rec["id"] = p.get("id")
    rec["title"] = p.get("title") or p.get("display_name")
    rec["publication_year"] = p.get("publication_year") or p.get("year")
    rec["authorships"] = p.get("authorships") or []
    ids = p.get("ids") or {}
    rec["doi"] = ids.get("doi") if isinstance(ids, dict) else p.get("doi")
    host = p.get("host_venue") or {}
    if isinstance(host, dict):
        rec["journal"] = {"name": host.get("display_name") or host.get("publisher")}
        rec["venue"] = host.get("display_name")
    else:
        rec["venue"] = p.get("venue")
    rec["abstract"] = p.get("abstract_inverted_index") or p.get("abstract") or ""
    rec["url"] = p.get("id") or p.get("url")
    return rec

def compose_reduce_summary(query: str, snippets: List[str]) -> str:
    # Cheap but robust reducer: select top representative snippets by length/position.
    if not snippets:
        return f"No abstracts/snippets found for query: {query}"
    # choose diverse representative sentences (first, median, last, plus top unique)
    out = [f"Automatic map-reduce summary for query: \"{query}\""]
    out.append(f"Collected {len(snippets)} small snippets (used for further LLM summarization).")
    sample = []
    if snippets:
        sample.append(snippets[0])
        sample.append(snippets[len(snippets)//2])
        sample.append(snippets[-1])
    # Add up to 20 unique long snippets
    long_snips = sorted(set(snippets), key=lambda s: -len(s))[:20]
    sample.extend(long_snips[:20])
    out.append("\nRepresentative snippets:\n")
    for s in sample[:20]:
        out.append("- " + s.replace("\n", " ")[:400])
    return "\n".join(out)

def run_pipeline(project_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    title = meta.get("title", "")
    max_papers = int(meta.get("max_papers", 7000))
    # Stage: discover
    redis_client.hset(JOB_META_PREFIX + project_id, mapping={"status": "discovering", "progress": "5"})
    papers = discover_papers_openalex(title, limit=max_papers)
    # normalize
    records = [normalize_record(p) for p in papers]
    # persist records to Redis (as JSON); for very large datasets, you should push to S3 and store url instead
    papers_key = JOB_META_PREFIX + project_id + JOB_PAPERS_SUFFIX
    try:
        redis_client.set(papers_key, json.dumps(records))
    except Exception as e:
        print("Could not persist papers list to Redis:", e)
    # small extractive snippets
    snippets = []
    for r in records:
        a = r.get("abstract") or ""
        if a:
            # pick first 1-2 sentences
            s = a.split(".")
            snippet = ".".join(s[:2]).strip()
            if snippet:
                snippets.append(snippet + ".")
    redis_client.hset(JOB_META_PREFIX + project_id, mapping={"status": "summarizing", "progress": "60"})
    # compose cheap reduce summary
    composed = compose_reduce_summary(title, snippets)
    # persist summary
    summary_obj = {"title": title, "num_papers": len(records), "composed_summary": composed}
    redis_client.hset(JOB_META_PREFIX + project_id, mapping={"summary": json.dumps(summary_obj), "status": "done", "progress": "100"})
    return summary_obj
