from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

from .models import Artifact, IncidentSession, SessionStatus


class IncidentStore:
    def __init__(self, path: str = "ops-copilot.db") -> None:
        self.path = path
        self.lock = threading.RLock()
        self._init()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, check_same_thread=False)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _init(self) -> None:
        with self.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(
              session_id TEXT PRIMARY KEY,title TEXT NOT NULL,status TEXT NOT NULL,
              operator_message TEXT NOT NULL,timeline TEXT NOT NULL,result TEXT,
              pending_action TEXT,trace TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts(
              artifact_id TEXT PRIMARY KEY,session_id TEXT NOT NULL,kind TEXT NOT NULL,
              original_name TEXT NOT NULL,stored_path TEXT NOT NULL,sha256 TEXT NOT NULL,
              size INTEGER NOT NULL,metadata TEXT NOT NULL,created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events(
              seq INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL,
              event TEXT NOT NULL,payload TEXT NOT NULL,created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals(
              session_id TEXT PRIMARY KEY,status TEXT NOT NULL,reviewer TEXT,comment TEXT,decided_at REAL
            );
            """)

    def create(self, title: str) -> IncidentSession:
        session = IncidentSession(uuid.uuid4().hex, title, SessionStatus.OPEN)
        now = time.time()
        with self.lock, self.connection() as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?)", (
                session.session_id,title,session.status.value,"","[]",None,None,"[]",now,now,
            ))
            self._event(db, session.session_id, "session_created", {"title": title})
        return session

    def get(self, session_id: str) -> IncidentSession:
        with self.connection() as db:
            row = db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            raise KeyError(session_id)
        return IncidentSession(row["session_id"],row["title"],SessionStatus(row["status"]),row["operator_message"],json.loads(row["timeline"]),json.loads(row["result"]) if row["result"] else None,json.loads(row["pending_action"]) if row["pending_action"] else None,json.loads(row["trace"]))

    def list(self, limit: int = 50) -> list[IncidentSession]:
        with self.connection() as db:
            ids=[row[0] for row in db.execute("SELECT session_id FROM sessions ORDER BY created_at DESC LIMIT ?",(limit,))]
        return [self.get(item) for item in ids]

    def update(self, session: IncidentSession, event: str = "session_updated", payload: dict | None = None) -> None:
        with self.lock, self.connection() as db:
            db.execute("UPDATE sessions SET title=?,status=?,operator_message=?,timeline=?,result=?,pending_action=?,trace=?,updated_at=? WHERE session_id=?",(
                session.title,session.status.value,session.operator_message,json.dumps(session.timeline),json.dumps(session.result) if session.result else None,json.dumps(session.pending_action) if session.pending_action else None,json.dumps(session.trace),time.time(),session.session_id,
            ))
            self._event(db,session.session_id,event,payload or {"status":session.status.value})

    def add_artifact(self, artifact: Artifact) -> None:
        with self.lock, self.connection() as db:
            db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)",(
                artifact.artifact_id,artifact.session_id,artifact.kind,artifact.original_name,artifact.stored_path,artifact.sha256,artifact.size,json.dumps(artifact.metadata),time.time(),
            ))
            self._event(db,artifact.session_id,"artifact_ingested",{"artifact_id":artifact.artifact_id,"kind":artifact.kind,"name":artifact.original_name})

    def artifacts(self, session_id: str) -> list[Artifact]:
        with self.connection() as db:
            rows=db.execute("SELECT * FROM artifacts WHERE session_id=? ORDER BY created_at",(session_id,)).fetchall()
        return [Artifact(r["artifact_id"],r["session_id"],r["kind"],r["original_name"],r["stored_path"],r["sha256"],r["size"],json.loads(r["metadata"])) for r in rows]

    def request_approval(self, session_id: str) -> None:
        with self.lock, self.connection() as db:
            db.execute("INSERT OR REPLACE INTO approvals(session_id,status) VALUES(?,'pending')",(session_id,))
            self._event(db,session_id,"approval_requested",{})

    def decide(self, session_id: str, approved: bool, reviewer: str, comment: str) -> None:
        with self.lock, self.connection() as db:
            changed=db.execute("UPDATE approvals SET status=?,reviewer=?,comment=?,decided_at=? WHERE session_id=? AND status='pending'",("approved" if approved else "rejected",reviewer,comment,time.time(),session_id)).rowcount
            if not changed: raise ValueError("approval is not pending")
            self._event(db,session_id,"approval_decided",{"approved":approved,"reviewer":reviewer})

    def approval(self, session_id: str) -> str | None:
        with self.connection() as db:
            row=db.execute("SELECT status FROM approvals WHERE session_id=?",(session_id,)).fetchone()
        return row[0] if row else None

    def events(self, session_id: str, after: int = 0) -> list[dict]:
        with self.connection() as db:
            rows=db.execute("SELECT seq,event,payload,created_at FROM events WHERE session_id=? AND seq>? ORDER BY seq",(session_id,after)).fetchall()
        return [{"seq":r["seq"],"event":r["event"],"payload":json.loads(r["payload"]),"created_at":r["created_at"]} for r in rows]

    @staticmethod
    def _event(db,session_id,event,payload):
        db.execute("INSERT INTO events(session_id,event,payload,created_at) VALUES(?,?,?,?)",(session_id,event,json.dumps(payload),time.time()))
