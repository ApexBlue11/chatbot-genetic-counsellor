import sqlite3
import os
import time
import json
from typing import List, Dict, Any, Optional


class BaseHistoryDB:
    """Abstract interface for swappable database memory adapters."""

    def create_conversation(self, title: str = "New Conversation") -> str:
        raise NotImplementedError

    def list_conversations(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def rename_conversation(self, conversation_id: str, title: str) -> None:
        raise NotImplementedError

    def delete_conversation(self, conversation_id: str) -> None:
        raise NotImplementedError

    def save_message(self, conversation_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        raise NotImplementedError

    def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def clear_session(self, conversation_id: str) -> None:
        raise NotImplementedError

    def save_file(self, conversation_id: str, filename: str, file_bytes: bytes, file_type: str) -> int:
        raise NotImplementedError

    def get_files(self, conversation_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError


class SQLiteHistoryDB(BaseHistoryDB):
    """Local SQLite memory client for development/staging."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_dir = "api_key"
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "chat_history.db")
        self.db_path = db_path
        self._init_db()

    def _execute(self, query: str, params: tuple = (), fetch: bool = False) -> List[Any]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if fetch:
                return cursor.fetchall()
            conn.commit()
            return []
        finally:
            conn.close()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)
            cursor.execute("PRAGMA table_info(chat_history)")
            columns = [info[1] for info in cursor.fetchall()]
            if "metadata" not in columns:
                cursor.execute("ALTER TABLE chat_history ADD COLUMN metadata TEXT")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_bytes BLOB NOT NULL,
                    file_type TEXT NOT NULL,
                    patient_label TEXT DEFAULT '',
                    uploaded_at REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)
            # Migrate: add patient_label column if missing
            cursor.execute("PRAGMA table_info(conversation_files)")
            file_cols = [info[1] for info in cursor.fetchall()]
            if "patient_label" not in file_cols:
                cursor.execute("ALTER TABLE conversation_files ADD COLUMN patient_label TEXT DEFAULT ''")
            conn.commit()
        finally:
            conn.close()

    # ── Conversations ──

    def create_conversation(self, title: str = "New Conversation") -> str:
        import uuid
        conv_id = str(uuid.uuid4())[:12]
        now = time.time()
        self._execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now),
        )
        return conv_id

    def list_conversations(self) -> List[Dict[str, Any]]:
        rows = self._execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC",
            fetch=True,
        )
        return [
            {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]}
            for r in rows
        ]

    def rename_conversation(self, conversation_id: str, title: str) -> None:
        self._execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), conversation_id),
        )

    def delete_conversation(self, conversation_id: str) -> None:
        self._execute("DELETE FROM chat_history WHERE conversation_id = ?", (conversation_id,))
        self._execute("DELETE FROM conversation_files WHERE conversation_id = ?", (conversation_id,))
        self._execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    # ── Messages ──

    def save_message(self, conversation_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        meta_json = json.dumps(metadata) if metadata else None
        now = time.time()
        self._execute(
            "INSERT INTO chat_history (conversation_id, role, content, metadata, timestamp) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, meta_json, now),
        )
        # Touch conversation updated_at
        self._execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )

    def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        rows = self._execute(
            "SELECT role, content, metadata, timestamp FROM chat_history WHERE conversation_id = ? ORDER BY timestamp ASC",
            (conversation_id,),
            fetch=True,
        )
        results = []
        for r in rows:
            entry = {"role": r[0], "content": r[1], "timestamp": r[3]}
            if r[2]:
                try:
                    entry["metadata"] = json.loads(r[2])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(entry)
        return results

    def clear_session(self, conversation_id: str) -> None:
        self._execute("DELETE FROM chat_history WHERE conversation_id = ?", (conversation_id,))

    # ── Files ──

    def save_file(self, conversation_id: str, filename: str, file_bytes: bytes, file_type: str) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO conversation_files (conversation_id, filename, file_bytes, file_type, uploaded_at) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, filename, file_bytes, file_type, time.time()),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_files(self, conversation_id: str) -> List[Dict[str, Any]]:
        rows = self._execute(
            "SELECT id, filename, file_type, uploaded_at FROM conversation_files WHERE conversation_id = ? ORDER BY uploaded_at ASC",
            (conversation_id,),
            fetch=True,
        )
        return [
            {"id": r[0], "filename": r[1], "file_type": r[2], "uploaded_at": r[3]}
            for r in rows
        ]

    def get_file_bytes(self, file_id: int) -> Optional[bytes]:
        rows = self._execute(
            "SELECT file_bytes FROM conversation_files WHERE id = ?",
            (file_id,),
            fetch=True,
        )
        return rows[0][0] if rows else None

    def get_file_by_type(self, conversation_id: str, file_type: str, patient_label: str = None) -> Optional[bytes]:
        """Return the bytes of the most recent file of a given type (optionally filtered by patient_label)."""
        if patient_label is not None:
            rows = self._execute(
                "SELECT file_bytes FROM conversation_files WHERE conversation_id = ? AND file_type = ? AND patient_label = ? ORDER BY uploaded_at DESC LIMIT 1",
                (conversation_id, file_type, patient_label),
                fetch=True,
            )
        else:
            rows = self._execute(
                "SELECT file_bytes FROM conversation_files WHERE conversation_id = ? AND file_type = ? ORDER BY uploaded_at DESC LIMIT 1",
                (conversation_id, file_type),
                fetch=True,
            )
        return rows[0][0] if rows else None

    def upsert_file(self, conversation_id: str, filename: str, file_bytes: bytes, file_type: str, patient_label: str = "") -> int:
        """Replace any existing file of this type+patient_label for this conversation, then insert fresh."""
        if patient_label:
            self._execute(
                "DELETE FROM conversation_files WHERE conversation_id = ? AND file_type = ? AND patient_label = ?",
                (conversation_id, file_type, patient_label)
            )
        else:
            self._execute(
                "DELETE FROM conversation_files WHERE conversation_id = ? AND file_type = ?",
                (conversation_id, file_type)
            )
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO conversation_files (conversation_id, filename, file_bytes, file_type, patient_label, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_id, filename, file_bytes, file_type, patient_label, time.time()),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_files_with_labels(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Return all files for a conversation including patient_label."""
        rows = self._execute(
            "SELECT id, filename, file_type, patient_label, uploaded_at FROM conversation_files WHERE conversation_id = ? ORDER BY uploaded_at ASC",
            (conversation_id,),
            fetch=True,
        )
        return [
            {"id": r[0], "filename": r[1], "file_type": r[2], "patient_label": r[3] or "", "uploaded_at": r[4]}
            for r in rows
        ]

    def count_vcf_files(self, conversation_id: str) -> int:
        """Count how many original VCF files have been uploaded to this conversation."""
        rows = self._execute(
            "SELECT COUNT(*) FROM conversation_files WHERE conversation_id = ? AND file_type = 'vcf'",
            (conversation_id,),
            fetch=True,
        )
        return rows[0][0] if rows else 0
