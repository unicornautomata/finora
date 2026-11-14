"""Upgrading an existing FINORA database (schema v1) must never lose or change accounting data."""
import shutil, sqlite3
from pathlib import Path

import pytest
from finora.server import migrate, services as S
from finora.server.db import Database
from finora.server.migrate import MigrationError


def build_v1(path) -> Database:
    """A database as the previous FINORA release would have left it: schema v1 and real-looking data."""
    db = Database(path, target_version=1)
    pw = S.hash_password
    with db.tx() as c:
        c.executemany("INSERT INTO users(username,full_name,pw_hash,role) VALUES (?,?,?,?)",
                      [("admin", "Administrator", pw("admin-pass"), "admin"), ("amy", "Amy", pw("amy-pass"), "accountant"),
                       ("vic", "Vic", pw("vic-pass"), "viewer")])
        c.executemany("INSERT INTO doc_types(doctype,description,prefix) VALUES (?,?,?)", [("GJ", "General Journal", "GJ-"), ("CDJ", "Cash Disbursements", "CD-")])
        c.execute("INSERT INTO coa(coa,description) VALUES ('C1','Main chart')")
        c.executemany("INSERT INTO gl_types(gltype,description,coa,normal_side) VALUES (?,?,?,?)", [("AST", "Assets", "C1", "D"), ("REV", "Revenue", "C1", "C")])
        c.executemany("INSERT INTO gl_accounts(glcd,description,gltype) VALUES (?,?,?)", [("1000", "Cash", "AST"), ("4000", "Sales", "REV")])
        c.executemany("INSERT INTO companies(cocd,name,currency,coa,tax_id) VALUES (?,?,?,?,?)", [("1000", "Acme Corp", "PHP", "C1", "123-456"), ("2000", "Beta Trading", "PHP", "C1", None)])
        c.execute("INSERT INTO partners(code,kind,name,glcd,cocd) VALUES ('CUST1','customer','First Customer','1000','1000')")

        def journal(cocd, amount_minor, status, no=None, reverses=None):
            cur = c.execute("""INSERT INTO journal_headers(cocd,doctype,doc_date,posting_date,entry_date,description,entered_by,reverses_id)
                               VALUES (?,?,?,?,?,?,?,?)""", (cocd, "GJ", "2026-03-01", "2026-03-01", "2026-03-01", f"{status} journal", "amy", reverses))
            h = cur.lastrowid
            dr, cr = ("4000", "1000") if reverses else ("1000", "4000")
            c.execute("INSERT INTO journal_lines(header_id,item_no,glcd,debit_minor,credit_minor) VALUES (?,1,?,?,0)", (h, dr, amount_minor))
            c.execute("INSERT INTO journal_lines(header_id,item_no,glcd,debit_minor,credit_minor) VALUES (?,2,?,0,?)", (h, cr, amount_minor))
            if status != "draft":
                c.execute("UPDATE journal_headers SET status='posted', doc_no=?, posted_by='amy', posted_at='2026-03-01T10:00:00Z', version=2 WHERE id=?", (no, h))
            return h
        j1 = journal("1000", 50000, "posted", "GJ-000001")
        j2 = journal("1000", 12345, "posted", "GJ-000002")
        rev = journal("1000", 12345, "posted", "GJ-000003", reverses=j2)
        c.execute("UPDATE journal_headers SET status='reversed', reversed_by_id=? WHERE id=?", (rev, j2))
        journal("1000", 999, "draft")
        journal("2000", 777700, "posted", "GJ-000001")
        c.executemany("INSERT INTO number_ranges(cocd,doctype,next_no) VALUES (?,?,?)", [("1000", "GJ", 4), ("2000", "GJ", 2)])
        c.executemany("INSERT INTO audit_log(ts,username,action,entity,entity_id,detail) VALUES (?,?,?,?,?,?)",
                      [("2026-03-01T10:00:00Z", "amy", "post", "journal", "1", "GJ-000001"), ("2026-03-01T10:05:00Z", "amy", "reverse", "journal", "2", "3")])
    return db


def raw_snapshot(path):
    c = sqlite3.connect(str(path))
    try:
        return migrate.snapshot(c)
    finally:
        c.close()


def raw_trial_balance(path, cocd):
    c = sqlite3.connect(str(path))
    try:
        return c.execute("""SELECT l.glcd, SUM(l.debit_minor), SUM(l.credit_minor) FROM journal_lines l JOIN journal_headers h ON h.id=l.header_id
                            WHERE h.cocd=? AND h.status IN ('posted','reversed') GROUP BY l.glcd ORDER BY 1""", (cocd,)).fetchall()
    finally:
        c.close()


def test_upgrade_preserves_every_existing_record_and_balance(tmp_path):
    path = tmp_path / "old.db"; build_v1(path)
    assert migrate.current_version(path) == 1
    before, tb_before = raw_snapshot(path), {k: raw_trial_balance(path, k) for k in ("1000", "2000")}

    db = Database(path)                                                    # <- the upgrade, exactly as the server does it at start-up

    assert migrate.current_version(path) == 2
    assert migrate.compare(before, raw_snapshot(path)) == []              # row counts, content hashes and totals identical
    assert before["tables"]["journal_lines"]["count"] == 10 and before["tables"]["users"]["count"] == 3
    with db.read() as c:
        assert {k: [tuple(r) for r in raw_trial_balance(path, k)] for k in ("1000", "2000")} == {k: [tuple(r) for r in v] for k, v in tb_before.items()}
        tb = S.trial_balance(c, "1000", "2099-12-31")
        # 1000: Dr 500.00 + 123.45 (original) / Cr 123.45 (its reversal); 4000 mirrors it. The draft is excluded.
        assert tb["balanced"] and [(r["glcd"], r["debit"], r["credit"]) for r in tb["rows"]] == [
            ("1000", "623.45", "123.45"), ("4000", "123.45", "623.45")]
        assert c.execute("PRAGMA foreign_key_check").fetchall() == [] and c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        # nobody lost their password
        for u, p in (("admin", "admin-pass"), ("amy", "amy-pass"), ("vic", "vic-pass")):
            assert S.verify_password(p, c.execute("SELECT pw_hash FROM users WHERE username=?", (u,)).fetchone()[0])


def test_upgrade_makes_a_verified_backup_that_still_holds_the_old_data(tmp_path):
    path = tmp_path / "old.db"; build_v1(path); before = raw_snapshot(path)
    db = Database(path)
    assert db.backup_path and Path(db.backup_path).exists() and ".bak-v1-" in db.backup_path.name
    assert migrate.current_version(db.backup_path) == 1 and migrate.compare(before, raw_snapshot(db.backup_path)) == []
    with db.read() as c:
        row = c.execute("SELECT version, name, backup_path FROM schema_history WHERE version=2").fetchone()
    assert tuple(row) == (2, "multicompany_foundation", str(db.backup_path))


def test_existing_companies_users_and_numbering_carry_over_into_the_new_model(tmp_path):
    path = tmp_path / "old.db"; build_v1(path); db = Database(path)
    admin = S.Principal(1, "admin", "admin")
    with db.read() as c:
        cos = [tuple(r) for r in c.execute("SELECT cocd, name, legal_name, status, group_id FROM companies ORDER BY cocd")]
        gid = c.execute("SELECT id FROM corporate_groups WHERE code='DEFAULT'").fetchone()[0]
        assert cos == [("1000", "Acme Corp", "Acme Corp", "active", gid), ("2000", "Beta Trading", "Beta Trading", "active", gid)]
        access = {r["username"]: (r["scope"], r["role_code"]) for r in c.execute(
            "SELECT u.username, a.scope, a.role_code FROM company_user_access a JOIN users u ON u.id=a.user_id")}
        assert access == {"admin": ("group", "GROUP_ADMIN"), "amy": ("group", "GROUP_ACCOUNTANT"), "vic": ("group", "AUDITOR")}
    with db.tx() as c:                                                      # the old workflow still works, numbering continues gaplessly
        j = S.journal_create(c, admin, dict(cocd="1000", doctype="GJ", doc_date="2026-04-01", posting_date="2026-04-01",
                                            lines=[dict(glcd="1000", debit="10.00"), dict(glcd="4000", credit="10.00")]))
        assert S.journal_post(c, admin, j["id"])["doc_no"] == "GJ-000004"
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):         # posted journals are still immutable
        with db.tx() as c:
            c.execute("UPDATE journal_lines SET debit_minor=1 WHERE header_id=1")


def test_reopening_an_up_to_date_database_makes_no_new_backup(tmp_path):
    path = tmp_path / "old.db"; build_v1(path); Database(path)
    n = len(list(tmp_path.glob("old.db.bak-*")))
    Database(path); Database(path)
    assert len(list(tmp_path.glob("old.db.bak-*"))) == n == 1


def test_fresh_database_needs_no_backup_and_has_no_default_group(tmp_path):
    db = Database(tmp_path / "new.db")
    assert db.backup_path is None and not list(tmp_path.glob("*.bak-*"))
    assert migrate.current_version(tmp_path / "new.db") == migrate.list_migrations()[-1].version
    with db.read() as c:
        assert c.execute("SELECT COUNT(*) FROM corporate_groups").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM company_roles").fetchone()[0] == 13


def test_backup_can_be_switched_off_explicitly(tmp_path):
    path = tmp_path / "old.db"; build_v1(path); Database(path, backup=False)
    assert not list(tmp_path.glob("old.db.bak-*"))


# ---------------------------------------------------------------- failure handling
def fake_migrations(tmp_path, body, name="003_test.sql", tag="migs"):
    d = tmp_path / tag; shutil.copytree(migrate.MIGRATIONS, d)
    (d / name).write_text(body, encoding="utf-8")
    return d


def upgraded_v2(tmp_path):
    path = tmp_path / "old.db"; build_v1(path); Database(path); return path


def test_a_failing_migration_rolls_back_completely_and_says_where_the_backup_is(tmp_path):
    path = upgraded_v2(tmp_path); before = raw_snapshot(path)
    d = fake_migrations(tmp_path, "CREATE TABLE half_done(a INTEGER);\nINSERT INTO table_that_does_not_exist VALUES (1);")
    with pytest.raises(MigrationError, match="rolled back.*backup"):
        Database(path, migrations_dir=d)
    c = sqlite3.connect(str(path))
    assert c.execute("PRAGMA user_version").fetchone()[0] == 2
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='half_done'").fetchone() is None     # even the first statement was undone
    c.close()
    assert migrate.compare(before, raw_snapshot(path)) == []


def test_a_migration_that_damages_accounting_data_is_refused_before_commit(tmp_path):
    path = upgraded_v2(tmp_path); before = raw_snapshot(path)
    d = fake_migrations(tmp_path, "DROP TRIGGER trg_line_del;\nDELETE FROM journal_lines WHERE header_id=1;")
    with pytest.raises(MigrationError, match="journal_lines row count changed"):
        Database(path, migrations_dir=d)
    assert migrate.current_version(path) == 2 and migrate.compare(before, raw_snapshot(path)) == []
    c = sqlite3.connect(str(path))
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='trg_line_del'").fetchone()          # the dropped trigger is back too
    c.close()


def test_silent_value_changes_are_caught_unless_the_migration_declares_them(tmp_path):
    path = upgraded_v2(tmp_path)
    sql = "UPDATE gl_accounts SET description = description || ' (renamed)';"
    with pytest.raises(MigrationError, match="gl_accounts content changed"):
        Database(path, migrations_dir=fake_migrations(tmp_path, sql, tag="undeclared"))
    assert migrate.current_version(path) == 2
    Database(path, migrations_dir=fake_migrations(tmp_path, "-- allow-data-change: gl_accounts\n" + sql, tag="declared"))
    c = sqlite3.connect(str(path))
    assert c.execute("SELECT description FROM gl_accounts WHERE glcd='1000'").fetchone()[0] == "Cash (renamed)"
    assert c.execute("PRAGMA user_version").fetchone()[0] == 3
    c.close()


def test_a_migration_may_not_change_posted_balances_even_if_it_declares_other_tables(tmp_path):
    path = upgraded_v2(tmp_path)
    d = fake_migrations(tmp_path, "-- allow-data-change: gl_accounts\nDROP TRIGGER trg_line_upd;\nUPDATE journal_lines SET debit_minor = debit_minor + 1 WHERE id = 1;")
    with pytest.raises(MigrationError):
        Database(path, migrations_dir=d)
    assert migrate.current_version(path) == 2


def test_restore_returns_the_database_to_its_pre_upgrade_state(tmp_path):
    path = tmp_path / "old.db"; build_v1(path); before = raw_snapshot(path)
    db = Database(path)
    with db.tx() as c:
        c.execute("DELETE FROM sessions"); c.execute("UPDATE users SET active=0")       # a bad day after the upgrade
    safety = migrate.restore_backup(db.backup_path, path)
    assert migrate.current_version(path) == 1 and migrate.compare(before, raw_snapshot(path)) == []
    assert safety and Path(safety).exists() and migrate.current_version(safety) == 2     # the post-upgrade file is kept, not destroyed
    Database(path)                                                                       # and upgrading again works
    assert migrate.current_version(path) == 2


def test_restore_refuses_a_damaged_or_missing_backup(tmp_path):
    path = tmp_path / "old.db"; build_v1(path)
    junk = tmp_path / "junk.bak"; junk.write_bytes(b"this is not a database" * 100)
    with pytest.raises(MigrationError):
        migrate.restore_backup(junk, path)
    with pytest.raises(MigrationError, match="not found"):
        migrate.restore_backup(tmp_path / "missing.bak", path)
    assert migrate.current_version(path) == 1


def test_command_line_status_check_and_dry_run(tmp_path, capsys):
    path = tmp_path / "old.db"; build_v1(path)
    assert migrate.main(["upgrade", "--db", str(path), "--dry-run"]) == 0
    assert '"pending": [\n    "002_multicompany_foundation"' in capsys.readouterr().out and migrate.current_version(path) == 1
    assert migrate.main(["upgrade", "--db", str(path)]) == 0 and migrate.current_version(path) == 2
    assert "Backup:" in capsys.readouterr().out
    assert migrate.main(["check", "--db", str(path)]) == 0
    assert migrate.main(["status", "--db", str(path)]) == 0 and '"pending": []' in capsys.readouterr().out
