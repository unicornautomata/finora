"""Desktop entry point.
   python -m finora.client            sign in to a server (local or remote)
   python -m finora.client --host     also run the server inside this app (multi-user host)"""
from __future__ import annotations
import argparse, sys

from PyQt6.QtWidgets import QApplication

from . import design
from .design.brand import app_icon
from .login import LoginDialog
from .shell import Shell


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--host", action="store_true")
    args, qt_args = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(design.PRODUCT_NAME); app.setWindowIcon(app_icon()); design.apply_theme(app, "light")
    state = dict(server=None, win=None)

    def start(initial: bool = False) -> bool:
        dlg = LoginDialog(host_default=args.host, server=state["server"])
        ok = dlg.exec()
        if dlg.server is not None:
            state["server"] = dlg.server                 # remember it so we reuse it after sign-out and stop it on exit
        if not ok:
            if not initial:
                app.quit()
            return False
        srv = state["server"]
        info = (f"Hosting on port {srv.port}. Other users connect to http://<this-computer>:{srv.port}"
                if srv and srv.host == "0.0.0.0" else ("Hosting locally (this computer only)" if srv else None))
        win = Shell(dlg.client, dlg.meta, info, on_logout=lambda: start(False))
        state["win"] = win; win.show()
        return True

    code = 0
    if start(initial=True):
        code = app.exec()
    if state["server"]:
        state["server"].stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
