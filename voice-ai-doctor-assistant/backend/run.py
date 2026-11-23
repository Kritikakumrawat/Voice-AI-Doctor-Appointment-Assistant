"""Start the API:  python run.py   (reads backend/.env)"""
import os

import uvicorn

from app.config import Settings

if __name__ == "__main__":
    s = Settings.from_env()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        log_level=s.log_level.lower(),
    )
