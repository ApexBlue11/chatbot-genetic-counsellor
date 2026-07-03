import os
import sys
sys.path.append('.')
from core.history_db import SQLiteHistoryDB

def test_db():
    print("Testing SQLiteHistoryDB initialization and persistence...")
    db_file = os.path.join("api_key", "test_chat_history.db")
    if os.path.exists(db_file):
        os.remove(db_file)
        
    db = SQLiteHistoryDB(db_path=db_file)
    
    # Test saving
    db.save_message("session_123", "user", "Hello assistant")
    db.save_message("session_123", "assistant", "Hello user, how can I help you?")
    
    # Test retrieval
    messages = db.get_messages("session_123")
    print(f"Retrieved {len(messages)} messages:")
    for msg in messages:
        print(f"[{msg['role']}] {msg['content']}")
        
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    
    # Test clear
    db.clear_session("session_123")
    messages_after = db.get_messages("session_123")
    print(f"Messages after clearing: {len(messages_after)}")
    assert len(messages_after) == 0
    
    os.remove(db_file)
    print("All db tests passed successfully!")

if __name__ == '__main__':
    test_db()
