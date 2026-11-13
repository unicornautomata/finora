"""HTTP API. Every capability the desktop client uses is available here, so a web front
end can be added later without touching business rules."""
from __future__ import annotations
import os
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import services as S
from .db import Database
from .definitions import DOCUMENT, ENTITIES


class LoginIn(BaseModel):
    username: str
    password: str


class JournalIn(BaseModel):
    cocd: Optional[str] = None
    doctype: Optional[str] = None
    doc_date: Optional[str] = None
    posting_date: Optional[str] = None
    reference: Optional[str] = None
    department: Optional[str] = None
    description: Optional[str] = None
    version: Optional[int] = None
    lines: Optional[list[dict[str, Any]]] = None


class ReverseIn(BaseModel):
    posting_date: Optional[str] = None


def build_app(db: Database) -> FastAPI:
    app = FastAPI(title="FINORA API", version="1.0")
    app.state.db = db

    origins = [o for o in os.environ.get("FINORA_CORS_ORIGINS", "").split(",") if o]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(S.ServiceError)
    async def service_error(_: Request, ex: S.ServiceError):
        return JSONResponse({"detail": ex.message}, status_code=ex.status)

    def auth(perm: str = "read"):
        def dep(authorization: Optional[str] = Header(None)) -> S.Principal:
            if not authorization or not authorization.lower().startswith("bearer "):
                raise S.ServiceError("Not authenticated", 401)
            p = S.principal_for(db, authorization[7:])
            if not p.can(perm):
                raise S.ServiceError("You do not have permission to do this", 403)
            return p
        return dep

    def entity_perm(entity: str, write: bool):
        def dep(authorization: Optional[str] = Header(None)) -> S.Principal:
            e = ENTITIES.get(entity)
            need = "admin" if (e and e.get("admin")) else ("write" if write else "read")
            return auth(need)(authorization)
        return dep

    # ---- system
    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/auth/login")
    def login(body: LoginIn):
        token, user = S.login(db, body.username, body.password)
        return {"token": token, "user": user}

    @app.post("/auth/logout")
    def logout(authorization: Optional[str] = Header(None), p: S.Principal = Depends(auth())):
        S.logout(db, authorization[7:])
        return {"status": "ok"}

    @app.get("/auth/me")
    def me(p: S.Principal = Depends(auth())):
        return {"username": p.username, "role": p.role}

    @app.get("/meta")
    def meta(p: S.Principal = Depends(auth())):
        ents = {k: v for k, v in ENTITIES.items() if not v.get("admin") or p.can("admin")}
        with db.read() as c:
            types = S.master_list(c, "doc_types")
        return dict(entities=ents, document=DOCUMENT, menu=S.menu_for(p), doc_types=types,
                    permissions=sorted(S.ROLE_PERMS[p.role]))

    # ---- master data (generic, definition-driven)
    @app.get("/master/{entity}")
    def master_list(entity: str, q: str = "", limit: int = 500, offset: int = 0,
                    authorization: Optional[str] = Header(None)):
        entity_perm(entity, False)(authorization)
        with db.read() as c:
            return S.master_list(c, entity, q, limit, offset)

    @app.get("/master/{entity}/{key}")
    def master_get(entity: str, key: str, authorization: Optional[str] = Header(None)):
        entity_perm(entity, False)(authorization)
        with db.read() as c:
            return S.master_get(c, entity, key)

    @app.post("/master/{entity}", status_code=201)
    def master_create(entity: str, body: dict[str, Any], authorization: Optional[str] = Header(None)):
        p = entity_perm(entity, True)(authorization)
        with db.tx() as c:
            return S.master_create(c, p, entity, body)

    @app.put("/master/{entity}/{key}")
    def master_update(entity: str, key: str, body: dict[str, Any], authorization: Optional[str] = Header(None)):
        p = entity_perm(entity, True)(authorization)
        with db.tx() as c:
            return S.master_update(c, p, entity, key, body)

    @app.delete("/master/{entity}/{key}")
    def master_delete(entity: str, key: str, authorization: Optional[str] = Header(None)):
        p = entity_perm(entity, True)(authorization)
        with db.tx() as c:
            S.master_delete(c, p, entity, key)
        return {"status": "deleted"}

    # ---- journals
    @app.get("/journals")
    def journals(cocd: str = "", doctype: str = "", status: str = "", q: str = "", limit: int = 200,
                 offset: int = 0, p: S.Principal = Depends(auth())):
        with db.read() as c:
            return S.journal_list(c, cocd, doctype, status, q, limit, offset)

    @app.get("/journals/{jid}")
    def journal(jid: int, p: S.Principal = Depends(auth())):
        with db.read() as c:
            return S.journal_get(c, jid)

    @app.post("/journals", status_code=201)
    def journal_create(body: JournalIn, p: S.Principal = Depends(auth("write"))):
        with db.tx() as c:
            return S.journal_create(c, p, body.model_dump(exclude_unset=True))

    @app.put("/journals/{jid}")
    def journal_update(jid: int, body: JournalIn, p: S.Principal = Depends(auth("write"))):
        with db.tx() as c:
            return S.journal_update(c, p, jid, body.model_dump(exclude_unset=True))

    @app.delete("/journals/{jid}")
    def journal_delete(jid: int, version: Optional[int] = None, p: S.Principal = Depends(auth("write"))):
        with db.tx() as c:
            S.journal_delete(c, p, jid, version)
        return {"status": "deleted"}

    @app.post("/journals/{jid}/post")
    def journal_post(jid: int, version: Optional[int] = None, p: S.Principal = Depends(auth("post"))):
        with db.tx() as c:
            return S.journal_post(c, p, jid, version)

    @app.post("/journals/{jid}/reverse")
    def journal_reverse(jid: int, body: ReverseIn = ReverseIn(), p: S.Principal = Depends(auth("post"))):
        with db.tx() as c:
            return S.journal_reverse(c, p, jid, body.posting_date)

    # ---- reports
    @app.get("/reports/trial-balance")
    def trial_balance(cocd: str, as_of: str = "", p: S.Principal = Depends(auth())):
        with db.read() as c:
            return S.trial_balance(c, cocd, as_of or None)

    return app
