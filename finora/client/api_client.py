"""Thin HTTP client. The desktop UI only ever talks to the server through this class,
whether the server runs in the same process (host mode) or on another machine."""
from __future__ import annotations
import httpx


class ApiError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None
        self.user: dict | None = None
        self._http = httpx.Client(base_url=self.base_url, timeout=15)

    def _req(self, method: str, path: str, **kw):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            r = self._http.request(method, path, headers=headers, **kw)
        except httpx.HTTPError as ex:
            raise ApiError(f"Cannot reach server at {self.base_url}: {ex}") from ex
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            if isinstance(detail, list):  # pydantic validation errors
                detail = "; ".join(str(d.get("msg", d)) for d in detail)
            raise ApiError(str(detail), r.status_code)
        return r.json()

    def login(self, username: str, password: str):
        out = self._req("POST", "/auth/login", json=dict(username=username, password=password))
        self.token, self.user = out["token"], out["user"]
        return out

    def logout(self):
        try:
            self._req("POST", "/auth/logout")
        except ApiError:
            pass
        self.token = None

    def meta(self): return self._req("GET", "/meta")
    def master_list(self, entity, q="", limit=1000): return self._req("GET", f"/master/{entity}", params=dict(q=q, limit=limit))
    def master_create(self, entity, data): return self._req("POST", f"/master/{entity}", json=data)
    def master_update(self, entity, key, data): return self._req("PUT", f"/master/{entity}/{key}", json=data)
    def master_delete(self, entity, key): return self._req("DELETE", f"/master/{entity}/{key}")
    def journals(self, **params): return self._req("GET", "/journals", params={k: v for k, v in params.items() if v})
    def journal(self, jid): return self._req("GET", f"/journals/{jid}")
    def journal_create(self, data): return self._req("POST", "/journals", json=data)
    def journal_update(self, jid, data): return self._req("PUT", f"/journals/{jid}", json=data)
    def journal_delete(self, jid, version=None): return self._req("DELETE", f"/journals/{jid}", params={"version": version} if version else None)
    def journal_post(self, jid, version=None): return self._req("POST", f"/journals/{jid}/post", params={"version": version} if version else None)
    def journal_reverse(self, jid, posting_date=None): return self._req("POST", f"/journals/{jid}/reverse", json=dict(posting_date=posting_date))
    def trial_balance(self, cocd, as_of=""): return self._req("GET", "/reports/trial-balance", params=dict(cocd=cocd, as_of=as_of))
