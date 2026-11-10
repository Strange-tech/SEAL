import os
import json
import time
import secrets
from datetime import datetime

DEFAULT_SESSION_DIR = ".sessions"

# --- Session Layer ---


class Session:
    def __init__(self, id, created_at="", history=None, session_dir=DEFAULT_SESSION_DIR):
        self.id = id
        self.created_at = created_at
        self.history = history if history is not None else []
        self.persisted = 0
        self.force_rewrite = False
        self.session_dir = session_dir

    def save(self):
        if self.force_rewrite:
            return self.rewrite_all()
        if len(self.history) == self.persisted:
            return
        return self.append_delta()

    def append_delta(self):
        with open(session_path(self.id, self.session_dir), "a", encoding="utf-8") as f:
            for msg in self.history[self.persisted:]:
                f.write(encode_record({"type": "message", "message": msg}))
        self.persisted = len(self.history)

    def rewrite_all(self):
        with open(session_path(self.id, self.session_dir), "w", encoding="utf-8") as f:
            f.write(encode_record({"type": "meta", "id": self.id, "created_at": self.created_at}))
            for msg in self.history:
                f.write(encode_record({"type": "message", "message": msg}))
        self.persisted = len(self.history)
        self.force_rewrite = False


def encode_record(rec):
    return json.dumps(rec, ensure_ascii=False) + "\n"


def new_session_id():
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4)


def session_path(id, session_dir=DEFAULT_SESSION_DIR):
    return os.path.join(session_dir, id + ".jsonl")


def new_session_file(history, session_dir=DEFAULT_SESSION_DIR):
    os.makedirs(session_dir, exist_ok=True)
    s = Session(new_session_id(), datetime.now().astimezone().isoformat(), history, session_dir=session_dir)
    with open(session_path(s.id, session_dir), "w", encoding="utf-8") as f:
        f.write(encode_record({"type": "meta", "id": s.id, "created_at": s.created_at}))
        for msg in history:
            f.write(encode_record({"type": "message", "message": msg}))
    s.persisted = len(history)
    return s


def load_session(id, session_dir=DEFAULT_SESSION_DIR):
    with open(session_path(id, session_dir), "rb") as f:
        data = f.read()
    n = data.rfind(b"\n")
    data = data[:n + 1] if n >= 0 else b""

    s = Session(id, session_dir=session_dir)
    for line in data.split(b"\n"):
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"Session file corrupted: {e}") from None
        if rec.get("type") == "meta":
            s.created_at = rec.get("created_at", "")
        elif rec.get("type") == "message":
            if rec.get("message") is not None:
                s.history.append(rec["message"])
    s.persisted = len(s.history)
    return s
