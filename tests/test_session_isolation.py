"""
Cross-session isolation for the shared demo deployment.

The app has no accounts and the demo is one public link over one SQLite file.
Before session scoping existed, `GET /api/conversations` returned every
conversation in the database, so each visitor saw — and could open, rename or
delete — everybody else's chats and uploaded VCFs.

These tests hold that boundary. Run against a live backend:

    python -m uvicorn api.main:app --port 8000
    python tests/test_session_isolation.py

Note this is an isolation boundary between anonymous visitors, not
authentication: anyone who learns another session's id can present it. The demo
must not be used with identifiable patient data.
"""

import sys

import requests

BASE = "http://localhost:8000/api"
ALICE = {"X-Session-Id": "alice-test-session"}
CAROL = {"X-Session-Id": "carol-test-session"}

failures = []


def check(name, condition, extra=""):
    print(f"  {'PASS' if condition else 'FAIL'}  {name}{'  ' + extra if extra else ''}")
    if not condition:
        failures.append(name)


def main():
    try:
        requests.get(f"{BASE}/health", timeout=5)
    except requests.RequestException:
        print("Backend not reachable on port 8000 — start it first.")
        return 2

    print(f"Session isolation\n{'=' * 58}")

    created = requests.post(f"{BASE}/conversations/",
                            json={"title": "Alice private case"}, headers=ALICE)
    check("a session can create a conversation", created.status_code == 200,
          str(created.status_code))
    if created.status_code != 200:
        return 1
    conv_id = created.json()["id"]

    # Give it a message so there is something worth leaking.
    requests.post(f"{BASE}/chat/", headers=ALICE, json={
        "conversation_id": conv_id, "user_input": "private note",
        "ai_enabled": False, "sv_enabled": False,
    })

    mine = requests.get(f"{BASE}/conversations/", headers=ALICE).json()
    theirs = requests.get(f"{BASE}/conversations/", headers=CAROL).json()
    check("the owner sees their own conversation",
          any(c["id"] == conv_id for c in mine))
    check("another session does not see it",
          not any(c["id"] == conv_id for c in theirs),
          f"other session sees {len(theirs)}")

    # Every route that takes a conversation id must refuse a foreign session.
    for label, response in [
        ("read messages", requests.get(f"{BASE}/conversations/{conv_id}/messages", headers=CAROL)),
        ("rename", requests.put(f"{BASE}/conversations/{conv_id}",
                                json={"title": "hijacked"}, headers=CAROL)),
        ("delete", requests.delete(f"{BASE}/conversations/{conv_id}", headers=CAROL)),
        ("post a message", requests.post(f"{BASE}/chat/", headers=CAROL, json={
            "conversation_id": conv_id, "user_input": "leak?",
            "ai_enabled": False, "sv_enabled": False})),
        ("upload a VCF", requests.post(
            f"{BASE}/upload/", headers=CAROL,
            data={"conversation_id": conv_id, "patient_label": "x"},
            files={"file": ("t.vcf", b"##fileformat=VCFv4.2\n", "text/plain")})),
    ]:
        # 404 rather than 403, so the response cannot confirm the id exists.
        check(f"a foreign session cannot {label}", response.status_code == 404,
              f"HTTP {response.status_code}")

    check("a request with no session header is rejected",
          requests.get(f"{BASE}/conversations/").status_code == 400)
    check("a malformed session id is rejected",
          requests.get(f"{BASE}/conversations/",
                       headers={"X-Session-Id": "../../etc/passwd"}).status_code == 400)

    survived = requests.get(f"{BASE}/conversations/{conv_id}/messages", headers=ALICE)
    check("the owner's conversation survived every attempt",
          survived.status_code == 200, f"HTTP {survived.status_code}")

    requests.delete(f"{BASE}/conversations/{conv_id}", headers=ALICE)

    print("=" * 58)
    print(f"{11 - len(failures)} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
