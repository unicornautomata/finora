"""Safe schema upgrades for existing FINORA databases.

Guarantees when an existing database is upgraded:
  1. A verified backup is written next to it first (SQLite online-backup API, WAL-safe).
  2. Each migration runs inside ONE transaction together with its version bump.
  3. Before COMMIT, every pre-existing accounting table is compared with a snapshot taken before the upgrade
     (row counts and content hashes of the original columns, plus debit/credit totals per company and status),
     and PRAGMA foreign_key_check must be clean. Any difference rolls the whole migration back.

Command line:
    python -m finora.server.migrate status  --db finora.db
    python -m finora.server.migrate upgrade --db finora.db [--dry-run]
    python -m finora.server.migrate check   --db finora.db
    python -m finora.server.migrate restore --db finora.db --backup finora.db.bak-v1-20261113T101500
"""
from __future__ import annotations
import argparse, hashlib, json, re, sqlite3, sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MIGRATIONS = Path(__file__).parent / "migrations"


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    allow_change: frozenset          # tables whose existing data this migration is allowed to change


def list_migrations(directory: Path | str | None = None) -> list[Migration]:
    out = []
    for f in sorted(Path(directory or MIGRATIONS).glob("*.sql")):
        m = re.match(r"(\d+)_(.+)\.sql$", f.name)
        if not m:
            continue
        head = f.read_text(encoding="utf-8").split("\n", 12)[:12]
        allow = set()
        for line in head:
            a = re.match(r"--\s*allow-data-change:\s*(.+)", line)
            if a:
                allow |= {t.strip() for t in a.group(1).split(",") if t.strip()}
        out.append(Migration(int(m.group(1)), m.group(2), f, frozenset(allow)))
    return out


# Columns that exist since migration 001. Content hashes use only these, so ADDING columns later is not data loss.
CORE = {
    "users": ["id", "username", "full_name", "pw_hash", "role", "active", "failed_attempts", "locked_until"],
    "coa": ["coa", "description"],
    "gl_types": ["gltype", "description", "coa", "normal_side"],
    "gl_accounts": ["glcd", "description", "gltype", "active"],
    "companies": ["cocd", "name", "currency", "coa", "tax_id"],
    "partners": ["code", "kind", "name", "glcd", "cocd"],
    "doc_types": ["doctype", "description", "prefix"],
    "number_ranges": ["cocd", "doctype", "next_no"],
    "journal_headers": ["id", "cocd", "doctype", "doc_no", "doc_date", "posting_date", "entry_date", "reference",
                        "department", "description", "status", "entered_by", "posted_by", "posted_at", "version",
                        "reverses_id", "reversed_by_id"],
    "journal_lines": ["id", "header_id", "item_no", "glcd", "description", "debit_minor", "credit_minor",
                      "partner_code", "qty_milli", "unit", "ref_item_no", "preceding_doc", "origin_ref", "product_desc"],
    "audit_log": ["id", "ts", "username", "action", "entity", "entity_id", "detail"],
}


def snapshot(c: sqlite3.Connection) -> dict:
    have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tables = {}
    for t, cols in CORE.items():
        if t not in have:
            continue
        h = hashlib.sha256(); n = 0
        for row in c.execute(f"SELECT {','.join(cols)} FROM {t} ORDER BY {','.join(cols)}"):
            h.update(json.dumps(list(row), default=str).encode()); n += 1
        tables[t] = dict(count=n, sha256=h.hexdigest())
    balances = []
    if "journal_headers" in have and "journal_lines" in have:
        balances = [list(r) for r in c.execute(
            """SELECT h.cocd, h.status, COUNT(DISTINCT h.id), SUM(l.debit_minor), SUM(l.credit_minor)
               FROM journal_headers h LEFT JOIN journal_lines l ON l.header_id = h.id
               GROUP BY h.cocd, h.status ORDER BY h.cocd, h.status""")]
    return dict(tables=tables, balances=balances)


def compare(before: dict, after: dict, allow=frozenset()) -> list[str]:
    problems = []
    for t, b in before["tables"].items():
        a = after["tables"].get(t)
        if a is None:
            problems.append(f"table {t} disappeared")
        elif t in allow:
            if a["count"] < b["count"]:
                problems.append(f"table {t} lost rows ({b['count']} -> {a['count']})")
        elif a["count"] != b["count"]:
            problems.append(f"table {t} row count changed ({b['count']} -> {a['count']})")
        elif a["sha256"] != b["sha256"]:
            problems.append(f"table {t} content changed")
    if before["balances"] != after["balances"] and not ({"journal_headers", "journal_lines"} & set(allow)):
        problems.append("journal debit/credit totals changed")
    return problems


def check_integrity(c: sqlite3.Connection) -> list[str]:
    problems = []
    bad = c.execute("PRAGMA foreign_key_check").fetchall()
    if bad:
        problems.append(f"{len(bad)} foreign key violation(s), first in table {bad[0][0]}")
    res = c.execute("PRAGMA integrity_check").fetchone()[0]
    if res != "ok":
        problems.append(f"integrity_check: {res}")
    return problems


def backup(db_path: str | Path, version: int) -> Path:
    src = Path(db_path)
    dst = src.with_name(f"{src.name}.bak-v{version}-{datetime.now().strftime('%Y%m%dT%H%M%S')}")
    n = 1
    while dst.exists():
        dst = src.with_name(f"{dst.name.split('-', 2)[0]}-{n}")      # same-second collisions
        n += 1
    s = sqlite3.connect(str(src)); d = sqlite3.connect(str(dst))
    try:
        with d:
            s.backup(d)
        ok = d.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        s.close(); d.close()
    if ok != "ok":
        dst.unlink(missing_ok=True)
        raise MigrationError(f"The backup could not be verified ({ok}); the database was not changed.")
    return dst


def restore_backup(backup_path: str | Path, target_path: str | Path) -> Path | None:
    """Replace the database with a backup. Stop every FINORA process that uses it first.
    The current file is kept as <db>.before-restore-<time>."""
    b, t = Path(backup_path), Path(target_path)
    if not b.exists():
        raise MigrationError(f"Backup not found: {b}")
    chk = sqlite3.connect(str(b))
    try:
        ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.DatabaseError as ex:               # not even a SQLite file
        ok = str(ex)
    finally:
        chk.close()
    if ok != "ok":
        raise MigrationError(f"The backup is damaged ({ok}); nothing was restored.")
    safety = None
    if t.exists():
        safety = t.with_name(f"{t.name}.before-restore-{datetime.now().strftime('%Y%m%dT%H%M%S')}")
        s = sqlite3.connect(str(t)); d = sqlite3.connect(str(safety))
        try:
            with d:
                s.backup(d)
        finally:
            s.close(); d.close()
        for suffix in ("-wal", "-shm"):
            Path(str(t) + suffix).unlink(missing_ok=True)
    s = sqlite3.connect(str(b)); d = sqlite3.connect(str(t))
    try:
        with d:
            s.backup(d)
    finally:
        s.close(); d.close()
    return safety


def current_version(db_path: str | Path) -> int:
    c = sqlite3.connect(str(db_path))
    try:
        return c.execute("PRAGMA user_version").fetchone()[0]
    finally:
        c.close()


def status(db_path: str | Path, directory=None) -> dict:
    p = Path(db_path)
    cur = current_version(p) if p.exists() else 0
    migs = list_migrations(directory)
    history = []
    if p.exists():
        c = sqlite3.connect(str(p))
        try:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='schema_history'").fetchone():
                history = [list(r) for r in c.execute("SELECT version, name, applied_at, backup_path FROM schema_history ORDER BY version")]
        finally:
            c.close()
    backups = sorted(x.name for x in p.parent.glob(p.name + ".bak-v*")) if p.exists() else []
    return dict(path=str(p), version=cur, latest=migs[-1].version if migs else 0,
                pending=[f"{m.version:03d}_{m.name}" for m in migs if m.version > cur], history=history, backups=backups)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m finora.server.migrate")
    ap.add_argument("command", choices=["status", "upgrade", "check", "restore"])
    ap.add_argument("--db", default="finora.db")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup", help="backup file to restore (restore command)")
    a = ap.parse_args(argv)
    if a.command == "status" or (a.command == "upgrade" and a.dry_run):
        st = status(a.db)
        print(json.dumps(st, indent=2))
        return 0
    if a.command == "check":
        c = sqlite3.connect(a.db)
        try:
            problems = check_integrity(c)
        finally:
            c.close()
        print("OK: integrity and foreign keys are clean" if not problems else "PROBLEMS:\n  " + "\n  ".join(problems))
        return 1 if problems else 0
    if a.command == "restore":
        if not a.backup:
            print("restore needs --backup <file>"); return 2
        safety = restore_backup(a.backup, a.db)
        print(f"Restored {a.db} from {a.backup}." + (f" The previous file was kept as {safety}." if safety else ""))
        return 0
    from .db import Database
    try:
        db = Database(a.db)
    except MigrationError as ex:
        print(f"UPGRADE FAILED: {ex}"); return 1
    print(f"Upgraded to version {status(a.db)['version']}." + (f" Backup: {db.backup_path}" if db.backup_path else " (no backup needed)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
