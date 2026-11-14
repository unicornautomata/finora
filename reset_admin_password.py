
from pathlib import Path
import sqlite3
import getpass

from finora.server.db import Database
from finora.server.services import hash_password, audit

# Change this if FINORA uses another database file.
db_path = Path("ledger.db")

if not db_path.exists():
    raise FileNotFoundError(f"Database not found: {db_path.resolve()}")

# Create a SQLite-consistent backup.
backup_path = db_path.with_name(db_path.stem + "_before_admin_recovery.db")

src = sqlite3.connect(str(db_path))
dst = sqlite3.connect(str(backup_path))
src.backup(dst)
dst.close()
src.close()

print(f"Backup created: {backup_path.resolve()}")

# Enter the new administrator password.
password = getpass.getpass("New admin password: ")
confirm = getpass.getpass("Confirm new password: ")

if not password or password != confirm:
    raise ValueError("Passwords are empty or do not match.")

db = Database(str(db_path))

with db.tx() as c:
    user = c.execute(
        "SELECT id FROM users WHERE username = ?",
        ("admin",)
    ).fetchone()

    if not user:
        raise ValueError("Admin account does not exist.")

    c.execute("""
        UPDATE users
        SET pw_hash = ?,
            failed_attempts = 0,
            locked_until = NULL
        WHERE username = ?
    """, (hash_password(password), "admin"))

    # Invalidate existing admin sessions.
    c.execute(
        "DELETE FROM sessions WHERE user_id = ?",
        (user["id"],)
    )

    audit(c, "system", "admin_password_reset", "users", "admin")

print("Admin account unlocked successfully.")
print("Admin password has been reset.")
print("You can now log in using:")
print("Username: admin")
