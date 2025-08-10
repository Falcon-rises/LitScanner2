import subprocess
import os
from flask import Flask

app = Flask(__name__)

@app.before_first_request
def launch_streamlit():
    subprocess.Popen(
        [
            "streamlit", "run", "frontend.py",
            "--server.port", "8501",
            "--server.address", "0.0.0.0"
        ],
        env=os.environ.copy()
    )

if __name__ != "__main__":
    # For Vercel
    handler = app
