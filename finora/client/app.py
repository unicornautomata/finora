"""Desktop entry point.
   python -m finora.client            sign in to a server (local or remote)
   python -m finora.client --host     also run the server inside this app (multi-user host)"""
from __future__ import annotations
import argparse, sys

from PyQt6.QtWidgets import QApplication

from . import design
from .api_client import ApiClient, ApiError
from .components import dialogs
from .design.brand import app_icon
from .login import LoginDialog
from .shell import Shell


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--host", action="store_true")
    args, qt_args = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(design.PRODUCT_NAME); app.setWindowIcon(app_icon()); design.apply_theme(app, "light")
    state = dict(server=None, win=None)

    def start():
        username, password = "", ""
        while True:
            dlg = LoginDialog(host_default=args.host, username=username, password=password)
            if not dlg.exec():
                return app.quit()
            try:
                if dlg.hosting and state["server"] is None:
                    from ..server.host import ServerThread
                    srv = ServerThread(dlg.db.text(), "0.0.0.0" if dlg.lan.isChecked() else "127.0.0.1", dlg.port.value())
                    srv.start()
                    if not srv.wait_ready():
                        raise ApiError("The server could not start (is the port already in use?)")
                    state["server"] = srv
                    if srv.initial_admin_password:
                        dialogs.info(None, "A new database was created.", "First run",
                                     detail=f"User: admin\nPassword: {srv.initial_admin_password}\n\nWrite this down now; it is shown only once. "
                                            "Change it under Administration → Users.")
                        username, password = "admin", srv.initial_admin_password
                        continue
                url = f"http://127.0.0.1:{state['server'].port}" if dlg.hosting else dlg.url.text().strip()
                client = ApiClient(url); client.login(dlg.user.text().strip(), dlg.pw.text())
                meta = client.meta()
            except ApiError as ex:
                dialogs.error(None, str(ex), "Cannot sign in"); username = dlg.user.text(); continue
            info = (f"Hosting on port {state['server'].port} — other users connect to http://<this-computer>:{state['server'].port}"
                    if state["server"] and state["server"].host == "0.0.0.0" else
                    ("Hosting locally (this computer only)" if state["server"] else None))
            win = Shell(client, meta, info, on_logout=start); state["win"] = win; win.show()
            return

    start()
    code = app.exec()
    if state["server"]:
        state["server"].stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
