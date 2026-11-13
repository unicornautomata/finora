"""SQLite access with a connection per request, WAL mode and explicit write transactions.

WAL lets many readers run while one writer commits. Writes use BEGIN IMMEDIATE so
concurrent writers queue on the busy timeout instead of failing half way through.
For many simultaneous users the same service layer can move to PostgreSQL.
"""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS = Path(__file__).parent / "migrations"


class Database:
    def __init__(self, path: str | Path):
        if sqlite3.sqlite_version_info < (3, 35, 0):
            raise RuntimeError(f"FINORA needs SQLite 3.35 or newer (found {sqlite3.sqlite_version}). On Windows use Python 3.10 or newer.")
        self.path = str(path)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA busy_timeout = 15000")
        return c

    @contextmanager
    def read(self):
        c = self.connect()
        try:
            yield c
        finally:
            c.close()

    @contextmanager
    def tx(self):
        c = self.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.execute("COMMIT")
        except BaseException:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    def migrate(self) -> None:
        c = self.connect()
        try:
            current = c.execute("PRAGMA user_version").fetchone()[0]
            for f in sorted(MIGRATIONS.glob("*.sql")):
                version = int(f.name.split("_")[0])
                if version > current:
                    c.executescript(f.read_text(encoding="utf-8"))
                    c.execute(f"PRAGMA user_version = {version}")
        finally:
            c.close()
