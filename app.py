"""
Hugging Face Spaces entrypoint.
HF Spaces expects a file called app.py in the root that starts the server.
"""
import uvicorn
from app.main import app  # noqa: F401 — imported so HF can also use it as ASGI

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=7860, workers=1)
