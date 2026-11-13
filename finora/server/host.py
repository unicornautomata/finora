"""Run the API inside another process (the PyQt6 app) on a background thread."""
from __future__ import annotations
import threading, time
import uvicorn

from .api import build_app
from .db import Database
from .services import seed_defaults


class ServerThread(threading.Thread):
    def __init__(self, db_path: str, host: str = "127.0.0.1", port: int = 8000):
        super().__init__(daemon=True, name="finora-server")
        self.db = Database(db_path)
        self.initial_admin_password = seed_defaults(self.db)
        self.host, self.port = host, port
        self.server = uvicorn.Server(uvicorn.Config(build_app(self.db), host=host, port=port,
                                                    log_level="warning", workers=1))

    def run(self):
        self.server.run()

    def wait_ready(self, timeout: float = 10.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if self.server.started:
                return True
            if not self.is_alive():
                return False
            time.sleep(0.05)
        return False

    def stop(self):
        self.server.should_exit = True
        self.join(timeout=5)
