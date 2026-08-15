from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from core.history_db import SQLiteHistoryDB
from core.session import require_session, verify_owns

router = APIRouter()
db = SQLiteHistoryDB()

class ConversationRename(BaseModel):
    title: str

@router.get("/")
def list_conversations(session_id: str = Depends(require_session)):
    return db.list_conversations(session_id)

@router.post("/")
def create_conversation(title: str = Body(embed=True),
                        session_id: str = Depends(require_session)):
    if not title:
        title = "New Conversation"
    conv_id = db.create_conversation(title, session_id=session_id)
    return {"id": conv_id, "title": title}

@router.get("/{conversation_id}/messages")
def get_messages(conversation_id: str, session_id: str = Depends(require_session)):
    verify_owns(db, conversation_id, session_id)
    return db.get_messages(conversation_id)

@router.put("/{conversation_id}")
def rename_conversation(conversation_id: str, rename: ConversationRename,
                        session_id: str = Depends(require_session)):
    verify_owns(db, conversation_id, session_id)
    db.rename_conversation(conversation_id, rename.title)
    return {"status": "success"}

@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str,
                        session_id: str = Depends(require_session)):
    verify_owns(db, conversation_id, session_id)
    db.delete_conversation(conversation_id)
    return {"status": "success"}
