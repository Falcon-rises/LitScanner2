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

@app.route("/")
def home():
    return "Streamlit app is running — visit / for your interface."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
