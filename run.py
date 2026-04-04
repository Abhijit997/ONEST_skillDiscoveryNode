"""Run the FastAPI backend and Streamlit UI together."""

import subprocess
import sys
import threading
import time

import uvicorn


def run_streamlit():
    """Launch Streamlit UI in a subprocess."""
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "ui/app.py",
         "--server.port", "8501", "--server.headless", "true"],
    )


if __name__ == "__main__":
    # Start Streamlit in a background thread
    st_thread = threading.Thread(target=run_streamlit, daemon=True)
    st_thread.start()

    print("\n  FastAPI  → http://localhost:8000/docs")
    print("  Streamlit → http://localhost:8501\n")

    # Start FastAPI (blocking)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
