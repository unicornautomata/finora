"""Copy master data from the old accountingdb.db into the new database.
   python -m ledger.server.import_legacy old/accountingdb.db --db ledger.db"""
import argparse, sqlite3
from .db import Database
from .services import seed_defaults


def run(old_path: str, new_path: str) -> dict:
    db = Database(new_path)
    seed_defaults(db)
    old = sqlite3.connect(old_path)
    old.row_factory = sqlite3.Row
    counts = {}

    def rows(sql):
        return [dict(r) for r in old.execute(sql)]

    with db.tx() as c:
        for r in rows("SELECT * FROM coannts"):
            c.execute("INSERT OR IGNORE INTO coa(coa,description) VALUES (?,?)", (r["coannts"], r["desc"]))
        for r in rows("SELECT * FROM gltypes"):
            c.execute("INSERT OR IGNORE INTO gl_types(gltype,description,coa) VALUES (?,?,?)",
                      (r["gltype"], r["desc"], r["coannts"]))
        for r in rows("SELECT * FROM glcd"):
            c.execute("INSERT OR IGNORE INTO gl_accounts(glcd,description,gltype) VALUES (?,?,?)",
                      (r["glcd"], r["desc"], r["gltype"]))
        for r in rows("SELECT * FROM companies"):
            c.execute("INSERT OR IGNORE INTO companies(cocd,name,currency,coa,tax_id) VALUES (?,?,?,?,?)",
                      (r["cocd"], r["coname"], r["loccurr"] or "USD", r["coannts"], r["taxid"]))
        for r in rows("SELECT * FROM doctypes"):
            c.execute("INSERT OR IGNORE INTO doc_types(doctype,description,prefix) VALUES (?,?,?)",
                      (r["doctype"], r["desc"], r["doctype"] + "-"))
        for table, kind, code, name in (("customers", "customer", "customer_code", "customer_name"),
                                        ("vendors", "vendor", "vendor_code", "vendor_name")):
            for r in rows(f"SELECT * FROM {table}"):
                key = r[code]
                if c.execute("SELECT 1 FROM partners WHERE code=?", (key,)).fetchone():
                    key = f"{key}-{kind[0].upper()}"          # codes were only unique per table before
                c.execute("INSERT OR IGNORE INTO partners(code,kind,name,glcd,cocd) VALUES (?,?,?,?,?)",
                          (key, kind, r[name], r["glcd"], r["cocd"]))
        for t in ("coa", "gl_types", "gl_accounts", "companies", "doc_types", "partners"):
            counts[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("--db", default="ledger.db")
    a = ap.parse_args()
    print(run(a.old, a.db))
