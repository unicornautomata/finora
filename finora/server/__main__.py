"""Headless server:  python -m finora.server --db finora.db --host 0.0.0.0 --port 8000"""
import argparse
from .host import ServerThread


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="finora.db")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    t = ServerThread(a.db, a.host, a.port)
    if t.initial_admin_password:
        print(f"Created user 'admin' with initial password: {t.initial_admin_password}")
    t.server.run()


if __name__ == "__main__":
    main()
