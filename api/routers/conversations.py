from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from core.history_db import SQLiteHistoryDB

router = APIRouter()
db = SQLiteHistoryDB()

class ConversationRename(BaseModel):
    title: str

@router.get("/")
def list_conversations():
    return db.list_conversations()

@router.post("/")
def create_conversation(title: str = Body(embed=True)):
    if not title:
        title = "New Conversation"
    conv_id = db.create_conversation(title)
    return {"id": conv_id, "title": title}

@router.get("/{conversation_id}/messages")
def get_messages(conversation_id: str):
    return db.get_messages(conversation_id)

@router.put("/{conversation_id}")
def rename_conversation(conversation_id: str, rename: ConversationRename):
    db.rename_conversation(conversation_id, rename.title)
    return {"status": "success"}

@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str):
    db.delete_conversation(conversation_id)
    return {"status": "success"}
