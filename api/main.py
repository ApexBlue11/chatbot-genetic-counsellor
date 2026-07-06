from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import chat, conversations, upload
from dotenv import load_dotenv

# Load local environment variables from .env file
load_dotenv()

app = FastAPI(
    title="VariantMind API",
    description="Backend API for the VariantMind Genetic Assistant",
    version="1.0.0"
)

# Allow React frontend to communicate
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev only. Should restrict in prod.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])

@app.get("/api/health")
def health_check():
    return {"status": "ok"}
