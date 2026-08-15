import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import chat, conversations, upload
from core.history_db import SQLiteHistoryDB
from dotenv import load_dotenv

# Load local environment variables from .env file
load_dotenv()

app = FastAPI(
    title="VariantMind API",
    description="Backend API for the VariantMind Genetic Assistant",
    version="1.0.0"
)

# Allow React frontend to communicate.
# ALLOWED_ORIGINS is a comma-separated list; set it to the deployed frontend's
# origin in production. It defaults to "*" for local development, which is fine
# there but should not be left as-is on a public deployment.
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Sessions travel in the X-Session-Id header, not cookies, so credentialed
    # requests are not needed — and "*" origins with credentials is invalid.
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])


@app.on_event("startup")
def purge_stale_demo_data():
    """Drop conversations nobody has touched for a while.

    A public demo accumulates abandoned sessions, and each one may hold an
    uploaded VCF. Bounding their lifetime keeps the database small and limits
    how long genomic data sits on disk. Set DEMO_RETENTION_HOURS to 0 to keep
    everything (the sensible choice for a private/local install).
    """
    hours = float(os.getenv("DEMO_RETENTION_HOURS", "48"))
    if hours <= 0:
        return
    try:
        removed = SQLiteHistoryDB().purge_older_than(hours * 3600)
        if removed:
            print(f"[startup] Purged {removed} conversation(s) older than {hours:g}h",
                  flush=True)
    except Exception as exc:                                      # noqa: BLE001
        print(f"[startup] Retention purge skipped: {exc}", flush=True)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
