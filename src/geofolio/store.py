"""Local SQLite workspace; one service process, durable configuration and audit."""

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        if os.name != "nt":
            os.chmod(path, 0o600)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS config(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER, body TEXT);
            CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, kind TEXT, body TEXT);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT, actor TEXT, action TEXT, detail TEXT);
        """)

    def config(self):
        row = self.db.execute("SELECT revision,body FROM config WHERE id=1").fetchone()
        return (row[0], json.loads(row[1])) if row else (0, None)

    def configure(self, portfolio, expected, actor="admin"):
        with self.db:
            current, _ = self.config()
            if current != expected:
                raise ValueError("Workspace changed; reload before saving")
            revision = current + 1
            self.db.execute(
                "INSERT OR REPLACE INTO config VALUES(1,?,?)", (revision, portfolio.model_dump_json())
            )
            self.db.execute("DELETE FROM records")
            self._audit(actor, "portfolio.updated", f"configuration revision {revision}")
        return revision

    def _audit(self, actor, action, detail):
        self.db.execute(
            "INSERT INTO audit(at,actor,action,detail) VALUES(?,?,?,?)",
            (datetime.now(UTC).isoformat(), actor, action, detail),
        )
        self.db.execute(
            "DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 1000)"
        )

    def audit(self, actor, action, detail=""):
        with self.db:
            self._audit(actor, action, detail)

    def record(self, kind, data):
        with self.db:
            self.db.execute("INSERT INTO records(kind,body) VALUES(?,?)", (kind, data.model_dump_json()))
            limit = 2001 if kind == "market" else 1000
            self.db.execute(
                "DELETE FROM records WHERE kind=? AND id NOT IN "
                "(SELECT id FROM records WHERE kind=? ORDER BY id DESC LIMIT ?)",
                (kind, kind, limit),
            )

    def remove_event(self, event_id):
        with self.db:
            self.db.execute(
                "DELETE FROM records WHERE kind='spatial' AND json_extract(body, '$.event_id')=?", (event_id,)
            )
            self._audit("admin", "scenario.removed", event_id)

    def records(self):
        return self.db.execute("SELECT kind,body FROM records ORDER BY id").fetchall()

    def audits(self):
        return [
            dict(zip(["at", "actor", "action", "detail"], row))
            for row in self.db.execute("SELECT at,actor,action,detail FROM audit ORDER BY id DESC LIMIT 100")
        ]

    def close(self):
        self.db.close()
