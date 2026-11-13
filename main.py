"""
Entrypoint for Vercel deployment of the TchueKAM FastAPI backend service.
"""

from tchuekam_backend.main import app

# Expose app for ASGI servers (Uvicorn, Vercel Serverless)
__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

