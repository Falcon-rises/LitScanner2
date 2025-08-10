import os
import time
import requests
import streamlit as st

# -----------------------------
# Configuration
# -----------------------------
# Use an environment variable for API_BASE, fallback to production URL
API_BASE = os.getenv("API_BASE", "https://your-backend-domain.com").rstrip("/")

st.set_page_config(page_title="LitScanner", layout="wide")

# -----------------------------
# Helper: Safe API Call
# -----------------------------
def safe_request(method, url, **kwargs):
    try:
        r = requests.request(method, url, timeout=15, **kwargs)
        if r.status_code >= 500:
            st.error(f"Server error {r.status_code}: {r.text}")
            return None
        r.raise_for_status()
        return r
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed: {e}")
        return None

# -----------------------------
# Functions
# -----------------------------
def search_papers(query):
    r = safe_request("GET", f"{API_BASE}/search", params={"query": query})
    if r:
        return r.json()
    return []

def get_status(job_id):
    r = safe_request("GET", f"{API_BASE}/status/{job_id}")
    if r:
        return r.json()
    return {}

def get_results(job_id):
    r = safe_request("GET", f"{API_BASE}/results/{job_id}")
    if r:
        return r.json()
    return {}

# -----------------------------
# Streamlit UI
# -----------------------------
st.title("📚 LitScanner")

query = st.text_input("Enter your search query:")
if st.button("Search"):
    if not query.strip():
        st.warning("Please enter a search query.")
    else:
        with st.spinner("Submitting search request..."):
            r = safe_request("POST", f"{API_BASE}/search", json={"query": query})
            if r:
                job_id = r.json().get("job_id")
                if not job_id:
                    st.error("No job ID received from backend.")
                else:
                    st.session_state.job_id = job_id
                    st.session_state.start_time = time.time()
                    st.info("Search submitted. Results will appear below.")

# -----------------------------
# Auto Refresh for Results
# -----------------------------
if "job_id" in st.session_state:
    job_id = st.session_state.job_id
    status_data = get_status(job_id)
    
    if not status_data:
        st.error("Unable to fetch status.")
    elif status_data.get("status") == "done":
        st.success("✅ Results ready!")
        results = get_results(job_id)
        if results:
            st.write(results)
    elif status_data.get("status") == "error":
        st.error("❌ An error occurred while processing your request.")
    else:
        st.warning("⏳ Still processing...")
        st.experimental_rerun()  # Re-run Streamlit script for polling
