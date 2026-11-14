"""SQLite access with a connection per request, WAL mode and explicit write transactions.

WAL lets many readers run while one writer commits. Writes use BEGIN IMMEDIATE so
concurrent writers queue on the busy timeout instead of failing half way through.
For many simultaneous users the same service layer can move to PostgreSQL.
"""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import migrate

MIGRATIONS = migrate.MIGRATIONS


class Database:
    def __init__(self, path: str | Path, migrations_dir: str | Path | None = None, target_version: int | None = None,
                 backup: bool = True):
        if sqlite3.sqlite_version_info < (3, 35, 0):
            raise RuntimeError(f"FINORA needs SQLite 3.35 or newer (found {sqlite3.sqlite_version}). On Windows use Python 3.10 or newer.")
        self.path = str(path)
        self.migrations_dir, self.target_version, self._backup = migrations_dir, target_version, backup
        self.backup_path: Path | None = None          # set when an upgrade of an existing database made a backup
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
        """Apply pending migrations. See finora/server/migrate.py for the safety guarantees."""
        todo_all = migrate.list_migrations(self.migrations_dir)
        c = self.connect()
        try:
            current = c.execute("PRAGMA user_version").fetchone()[0]
            todo = [m for m in todo_all if m.version > current and (self.target_version is None or m.version <= self.target_version)]
            if not todo:
                return
            before = None
            if current > 0:
                if self._backup:
                    self.backup_path = migrate.backup(self.path, current)
                before = migrate.snapshot(c)
            for m in todo:
                try:
                    c.executescript("BEGIN IMMEDIATE;\n" + m.path.read_text(encoding="utf-8")
                                    + f"\nPRAGMA user_version = {m.version};")
                    problems = []
                    if before is not None:
                        after = migrate.snapshot(c)
                        problems += migrate.compare(before, after, m.allow_change)
                        before = after
                    problems += migrate.check_integrity(c)
                    if problems:
                        raise migrate.MigrationError("; ".join(problems))
                    c.execute("COMMIT")
                except BaseException as ex:
                    if c.in_transaction:
                        c.execute("ROLLBACK")
                    saved = f" A backup of the original is at {self.backup_path}." if self.backup_path else ""
                    raise migrate.MigrationError(
                        f"Upgrade step {m.version:03d}_{m.name} failed and was rolled back, so your data is unchanged.{saved} "
                        f"Cause: {ex}") from ex
            if self.backup_path and c.execute("SELECT 1 FROM sqlite_master WHERE name='schema_history'").fetchone():
                c.execute("UPDATE schema_history SET backup_path=? WHERE version=?", (str(self.backup_path), todo[0].version))
        finally:
            c.close()
