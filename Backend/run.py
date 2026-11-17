#!/usr/bin/env python3
"""
Entry point script to start the ARRT User Data Extractor FastAPI server.
Usage:
    python run.py
"""
import os
import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() in ("true", "1", "yes")

    print(f"Starting ARRT Extractor on http://{host}:{port} (Swagger docs: http://{host}:{port}/docs)")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )

