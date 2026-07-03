import sys
sys.path.append('.')
import os
from core.history_db import SQLiteHistoryDB


def test_conversations():
    print("Testing conversation CRUD...")
    db_file = os.path.join("api_key", "test_conv_db.db")
    if os.path.exists(db_file):
        os.remove(db_file)

    db = SQLiteHistoryDB(db_path=db_file)

    # Create conversations
    c1 = db.create_conversation("BRCA2 Analysis")
    c2 = db.create_conversation("VCF Patient #12")
    print(f"  Created conversations: {c1}, {c2}")

    # List
    convs = db.list_conversations()
    assert len(convs) == 2, f"Expected 2 conversations, got {len(convs)}"
    print(f"  Listed {len(convs)} conversations")

    # Rename
    db.rename_conversation(c1, "BRCA2 rs80359876 Analysis")
    convs = db.list_conversations()
    renamed = [c for c in convs if c["id"] == c1][0]
    assert renamed["title"] == "BRCA2 rs80359876 Analysis"
    print(f"  Renamed: {renamed['title']}")

    # Messages with metadata
    db.save_message(c1, "user", "Analyze rs80359876")
    db.save_message(c1, "assistant", "Pathogenic", metadata={"type": "variant_analysis", "variant_id": "rs80359876"})
    msgs = db.get_messages(c1)
    assert len(msgs) == 2
    assert msgs[1].get("metadata", {}).get("variant_id") == "rs80359876"
    print(f"  Messages: {len(msgs)}, metadata preserved")

    # File storage
    test_bytes = b"##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\n"
    fid = db.save_file(c1, "test.vcf", test_bytes, "vcf")
    files = db.get_files(c1)
    assert len(files) == 1
    retrieved = db.get_file_bytes(fid)
    assert retrieved == test_bytes
    print(f"  File stored and retrieved: {files[0]['filename']}")

    # Delete conversation
    db.delete_conversation(c2)
    convs = db.list_conversations()
    assert len(convs) == 1
    print(f"  Deleted c2, remaining: {len(convs)}")

    # Cleanup
    db.delete_conversation(c1)
    os.remove(db_file)
    print("All conversation DB tests passed!")


if __name__ == '__main__':
    test_conversations()
