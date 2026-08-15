"""
Anonymous per-browser session scoping.

The app has no accounts, and the demo is a single shared link over a single
SQLite file. Without scoping, `list_conversations` returned every conversation
in the database, so each visitor saw — and could open, rename or delete —
everybody else's chats and uploaded VCFs.

Each browser generates a random id, stores it locally and sends it as
``X-Session-Id``. It is an isolation boundary between casual demo visitors, not
an authentication mechanism: anyone who learns another session's id can present
it. That is an acceptable trade for an anonymous demo, but it means the app
still must not be used with identifiable patient data.
"""

import re
from fastapi import Header, HTTPException

SESSION_HEADER = "X-Session-Id"
_VALID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def require_session(x_session_id: str = Header(default="")) -> str:
    """Extract and validate the caller's session id."""
    session_id = (x_session_id or "").strip()
    if not session_id:
        raise HTTPException(
            status_code=400,
            detail=f"Missing {SESSION_HEADER} header. Reload the page to get a new session.",
        )
    if not _VALID.match(session_id):
        raise HTTPException(status_code=400, detail=f"Malformed {SESSION_HEADER} header.")
    return session_id


def verify_owns(db, conversation_id: str, session_id: str) -> None:
    """Reject access to a conversation belonging to a different session.

    Returns 404 rather than 403 so an unrelated session cannot use the response
    to confirm that a given conversation id exists.
    """
    if not db.owns_conversation(conversation_id, session_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
