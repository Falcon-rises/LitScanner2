import streamlit as st
import requests
import time
import json

# ==============================
# CONFIGURATION
# ==============================
# Use your deployed backend URL (replace with your actual working Vercel API endpoint)
API_BASE = "https://lit-scanner2.vercel.app"  # Make sure this matches your backend deployment

st.set_page_config(page_title="LitScanner", layout="wide")

st.title("📚 LitScanner – Literature Collection Tool")
st.write("Search, track, and download papers in APA format.")

# ==============================
# INPUT: PROJECT ID
# ==============================
project_id = st.text_input("Enter Project ID:")

if st.button("Check Status") and project_id:
    with st.spinner("Fetching project status..."):
        try:
            r = requests.get(f"{API_BASE}/api/projects/{project_id}/status", timeout=10)
            if r.status_code == 200:
                data = r.json()
                st.success(f"Status: {data.get('status', 'Unknown')}")
            else:
                st.error(f"Error {r.status_code}: {r.text}")
        except requests.RequestException as e:
            st.error(f"Connection error: {e}")

# ==============================
# FETCH PAPERS
# ==============================
if st.button("Get Papers") and project_id:
    with st.spinner("Downloading papers..."):
        try:
            r = requests.get(f"{API_BASE}/api/projects/{project_id}/papers", timeout=20)
            if r.status_code == 200:
                papers = r.json()
                st.session_state["papers"] = papers
                st.success(f"Fetched {len(papers)} papers.")
            else:
                st.error(f"Error {r.status_code}: {r.text}")
        except requests.RequestException as e:
            st.error(f"Connection error: {e}")

# ==============================
# DISPLAY & DOWNLOAD
# ==============================
if "papers" in st.session_state and st.session_state["papers"]:
    st.subheader("📄 Papers List")
    for p in st.session_state["papers"]:
        st.markdown(f"**{p.get('title','Untitled')}** — {p.get('authors','Unknown')}")
    
    # Format APA 7th style
    st.subheader("📑 Download APA 7th Bibliography")
    apa_formatted = "\n".join(
        [f"{p.get('authors','')}. ({p.get('year','n.d.')}). {p.get('title','')}. {p.get('source','')}" 
         for p in st.session_state["papers"]]
    )
    st.download_button(
        "Download Bibliography",
        apa_formatted,
        file_name="bibliography.txt",
        mime="text/plain"
    )

# ==============================
# FOOTER
# ==============================
st.markdown("---")
st.caption("LitScanner © 2025 • Built with ❤️ for researchers")
