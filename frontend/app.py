# app.py
# Streamlit frontend: modern layout, progress, countdown, APA export.
import os
import time
import json
import requests
import streamlit as st
from datetime import datetime, timedelta
from typing import List, Dict

API_BASE = os.getenv("API_BASE", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="LitHybrid — Research Summarizer", layout="wide", initial_sidebar_state="expanded")
st.markdown("<style> .big-font {font-size:22px;} .muted {color:#6c757d;} </style>", unsafe_allow_html=True)

st.title("LitHybrid — Scholarly Title → 7k Paper Summaries")
st.write("Enter a title, start a job. Worker will fetch ~papers, compute, and store summary. Frontend shows progress & countdown.")

with st.sidebar:
    st.header("New project")
    title = st.text_input("Title to search", "")
    max_papers = st.number_input("Max papers (cap)", min_value=50, max_value=70000, value=7000, step=50)
    expected_mins = st.number_input("Expected time (mins)", min_value=1, max_value=1440, value=30)
    start_btn = st.button("Start job")

if "project_id" not in st.session_state:
    st.session_state["project_id"] = None
    st.session_state["expected_end"] = None

def api_post(path, payload):
    url = API_BASE + path
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def api_get(path, params=None):
    url = API_BASE + path
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

if start_btn and title.strip():
    payload = {"title": title.strip(), "max_papers": max_papers, "expected_time_minutes": expected_mins}
    try:
        res = api_post("/api/projects", payload)
        st.session_state["project_id"] = res["project_id"]
        st.session_state["expected_end"] = datetime.utcnow() + timedelta(minutes=int(res.get("expected_time_minutes", expected_mins)))
        st.success(f"Started job: {res['project_id']}")
    except Exception as e:
        st.error(f"Could not start job: {e}")

if st.session_state.get("project_id"):
    pid = st.session_state["project_id"]
    st.subheader("Job status")
    status_box = st.empty()
    progress_bar = st.progress(0)
    countdown_box = st.empty()
    summary_box = st.empty()
    papers_box = st.empty()

    # poll loop (non-blocking via button or manual)
    if st.button("Refresh status"):
        try:
            s = api_get(f"/api/projects/{pid}/status")
            status_box.json(s)
            try:
                progress_bar.progress(int(s.get("progress", 0)))
            except Exception:
                pass
            # countdown
            if st.session_state.get("expected_end"):
                remaining = st.session_state["expected_end"] - datetime.utcnow()
                seconds = int(remaining.total_seconds())
                if seconds < 0:
                    countdown_box.markdown("**Countdown:** 00:00:00 (should be done)")
                else:
                    hrs, rem = divmod(seconds, 3600)
                    mins, secs = divmod(rem, 60)
                    countdown_box.markdown(f"**Countdown:** {hrs:02d}:{mins:02d}:{secs:02d}")
        except Exception as e:
            st.error(f"Status fetch error: {e}")

    if st.button("Auto-poll until done (recommended for long jobs)"):
        with st.spinner("Polling..."):
            while True:
                try:
                    s = api_get(f"/api/projects/{pid}/status")
                    status_box.json(s)
                    try:
                        progress_bar.progress(int(s.get("progress", 0)))
                    except Exception:
                        pass
                    if s.get("status") in ("done", "error", "failed"):
                        break
                except Exception as e:
                    st.error(f"Polling error: {e}")
                    break
                time.sleep(3)
    # show summary if ready
    try:
        summ = api_get(f"/api/projects/{pid}/summary")
        summary_box.markdown("### Summary (auto-composed)")
        summary_box.write(summ.get("summary", {}).get("composed_summary", "No summary yet"))
    except Exception:
        summary_box.info("Summary not ready yet.")

    if st.button("Fetch first page of papers (preview)"):
        try:
            p = api_get(f"/api/projects/{pid}/papers", params={"page": 1, "per_page": 50})
            papers_box.write(p)
            st.session_state["papers_preview"] = p.get("papers", [])
        except Exception as e:
            st.error(f"Could not fetch papers: {e}")

    if st.session_state.get("papers_preview"):
        st.markdown("### APA 7 Preview (first 10)")
        def format_authors(aulist):
            if not aulist:
                return ""
            names = []
            for item in aulist:
                a = item.get("author") if isinstance(item, dict) else None
                if a:
                    display = a.get("display_name") or ""
                else:
                    display = item.get("name") if isinstance(item, dict) else str(item)
                parts = display.split()
                if len(parts) == 0:
                    continue
                last = parts[-1]
                initials = " ".join([f"{p[0].upper()}." for p in parts[:-1]])
                names.append(f"{last}, {initials}".strip())
            n = len(names)
            if n == 1:
                return names[0]
            if 2 <= n <= 20:
                return ", ".join(names[:-1]) + ", & " + names[-1]
            return ", ".join(names[:19]) + ", ... " + names[-1]

        preview = st.session_state["papers_preview"][:10]
        for i, rec in enumerate(preview, start=1):
            authors = format_authors(rec.get("authorships", []))
            title_t = rec.get("title", "")
            year = rec.get("publication_year", "n.d.")
            venue = (rec.get("journal") or {}).get("name") or rec.get("venue") or ""
            doi = rec.get("doi") or ""
            entry = f"{authors} ({year}). {title_t}. {venue}. {('https://doi.org/'+doi) if doi else (rec.get('url') or '')}"
            st.markdown(f"**{i}.** {entry}")

    if st.button("Export full APA text (server-side pagination + stream)"):
        # fetch all pages and build file locally (warning for very large)
        try:
            # fetch total first
            p0 = api_get(f"/api/projects/{pid}/papers", params={"page":1,"per_page":1})
            total = p0.get("total", 0)
            per_page = 1000
            pages = (total + per_page - 1) // per_page
            st.info(f"Exporting {total} papers in {pages} pages. This may take time.")
            tmp_lines = []
            for pg in range(1, pages+1):
                p = api_get(f"/api/projects/{pid}/papers", params={"page":pg,"per_page":per_page})
                papers = p.get("papers", [])
                for idx, rec in enumerate(papers, start=(pg-1)*per_page+1):
                    authors = format_authors(rec.get("authorships", []))
                    title_t = rec.get("title", "")
                    year = rec.get("publication_year", "n.d.")
                    venue = (rec.get("journal") or {}).get("name") or rec.get("venue") or ""
                    doi = rec.get("doi") or ""
                    entry = f"{authors} ({year}). {title_t}. {venue}. {('https://doi.org/'+doi) if doi else (rec.get('url') or '')}"
                    tmp_lines.append(f"{idx}. {entry}")
                st.info(f"Fetched page {pg}/{pages}")
            txt = "\n".join(tmp_lines)
            st.download_button("Download APA (txt)", data=txt, file_name=f"bibliography_{pid}_APA7.txt", mime="text/plain")
        except Exception as e:
            st.error(f"Export failed: {e}")
