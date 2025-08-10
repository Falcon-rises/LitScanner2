import os
import time
import requests
import redis
from dotenv import load_dotenv

# Load environment variables (useful for local dev)
load_dotenv()

# --------------------------
# Redis Setup
# --------------------------
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL is not set. Please configure it in environment variables.")

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
except Exception as e:
    raise RuntimeError(f"Failed to connect to Redis: {e}")

# --------------------------
# OpenAlex Search
# --------------------------
def search_openalex(query, filters=None, limit=20):
    """
    Search OpenAlex for works matching the query.
    Limit reduced to 20 for Vercel safety.
    """
    base_url = "https://api.openalex.org/works"
    params = {"search": query, "per-page": 20}
    if filters:
        params.update(filters)

    results = []
    url = base_url

    try:
        while url and len(results) < limit:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            results.extend(data.get("results", []))
            url = data.get("meta", {}).get("next_cursor", None)

            time.sleep(0.1)  # polite delay
    except requests.exceptions.RequestException as e:
        print(f"OpenAlex API error: {e}")
    except ValueError:
        print("Invalid JSON from OpenAlex")

    return results[:limit]

# --------------------------
# Normalize Paper Record
# --------------------------
def normalize_record(paper):
    """
    Convert OpenAlex paper data into a uniform dict.
    """
    try:
        abstract_data = paper.get("abstract_inverted_index", None)
        abstract = ""
        if abstract_data:
            # reconstruct abstract text
            inverted = {word: pos for word, pos in abstract_data.items()}
            max_pos = max([pos for positions in inverted.values() for pos in positions])
            words = [""] * (max_pos + 1)
            for word, positions in abstract_data.items():
                for pos in positions:
                    words[pos] = word
            abstract = " ".join(words)

        return {
            "id": paper.get("id"),
            "title": paper.get("title"),
            "authors": [a.get("author", {}).get("display_name") for a in paper.get("authorships", [])],
            "publication_year": paper.get("publication_year"),
            "abstract": abstract,
            "doi": paper.get("doi"),
            "url": paper.get("primary_location", {}).get("source", {}).get("homepage_url"),
        }
    except Exception as e:
        print(f"Error normalizing record: {e}")
        return None

# --------------------------
# Pipeline Runner
# --------------------------
def run_pipeline(query, limit=20, job_id=None):
    """
    Runs search and stores results in Redis.
    """
    job_key = f"job:{job_id}" if job_id else f"job:{int(time.time())}"
    redis_client.set(job_key, "running")

    papers = search_openalex(query, limit=limit)
    normalized_papers = [normalize_record(p) for p in papers if p]

    # Store in Redis
    redis_client.set(job_key, "completed")
    redis_client.set(f"{job_key}:data", str(normalized_papers))

    return {"job_id": job_key, "count": len(normalized_papers)}

# --------------------------
# Quick Local Test
# --------------------------
if __name__ == "__main__":
    result = run_pipeline("artificial intelligence", limit=5, job_id="testjob")
    print(result)
