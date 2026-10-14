import json
import os
import sqlite3
from pathlib import Path


class Storage:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("BINGO_DATA_DIR", "data"))
        self.path.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS records (kind TEXT, name TEXT, value TEXT, PRIMARY KEY(kind,name))"
            )
        if os.name != "nt":
            self.path.chmod(0o700)
            (self.path / "bingo.sqlite3").chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.path / "bingo.sqlite3")

    def save(self, kind, name, value):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO records VALUES (?,?,?)",
                (kind, name, json.dumps(value)),
            )

    def load(self, kind, name):
        with self.connect() as db:
            row = db.execute(
                "SELECT value FROM records WHERE kind=? AND name=?", (kind, name)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind):
        with self.connect() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT name FROM records WHERE kind=? ORDER BY name", (kind,)
                )
            ]
