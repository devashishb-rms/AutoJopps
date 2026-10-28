"""Google sign-in (OIDC) with a demo fallback, cookie sessions, Gmail connect."""
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db, User, Profile

router = APIRouter(prefix="/api/auth", tags=["auth"])
signer = URLSafeTimedSerializer(settings.SECRET, salt="session")
COOKIE = "aj_session"
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


def set_session(resp: Response, user_id: int):
    resp.set_cookie(COOKIE, signer.dumps({"uid": user_id}), httponly=True, samesite="lax", max_age=14 * 86400)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    tok = request.cookies.get(COOKIE)
    if not tok:
        raise HTTPException(401, "not signed in")
    try:
        data = signer.loads(tok, max_age=14 * 86400)
    except BadSignature:
        raise HTTPException(401, "bad session")
    u = db.get(User, data["uid"])
    if not u:
        raise HTTPException(401, "unknown user")
    return u


def ensure_profile(db: Session, user: User) -> Profile:
    p = db.query(Profile).filter_by(user_id=user.id).first()
    if not p:
        p = Profile(user_id=user.id, data={}, preferences={}, target_jds=[], notify={})
        db.add(p)
        db.flush()
    return p


def user_out(u: User):
    return {"id": u.id, "email": u.email, "name": u.name, "picture": u.picture,
            "gmail_connected": u.gmail_connected, "onboarding_step": u.onboarding_step,
            "agent_enabled": u.agent_enabled, "approval_mode": u.approval_mode}


@router.get("/config")
def auth_config():
    return {"modes": settings.modes(), "plans_url": "/api/billing/plans"}


# ---------- Google OIDC ----------
@router.get("/google/start")
def google_start(request: Request, gmail: int = 0):
    if not settings.google_enabled:
        raise HTTPException(400, "Google sign-in not configured; use demo sign-in")
    state = secrets.token_urlsafe(16) + ("|gmail" if gmail else "")
    scope = "openid email profile"
    if gmail and settings.GOOGLE_GMAIL_SCOPE:
        scope += " https://www.googleapis.com/auth/gmail.readonly"
    params = {"client_id": settings.GOOGLE_CLIENT_ID, "redirect_uri": settings.BASE_URL + "/api/auth/google/callback",
              "response_type": "code", "scope": scope, "state": state, "access_type": "offline",
              "prompt": "consent" if gmail else "select_account", "include_granted_scopes": "true"}
    resp = RedirectResponse(GOOGLE_AUTH + "?" + urlencode(params))
    resp.set_cookie("aj_oauth_state", state, httponly=True, max_age=600)
    return resp


@router.get("/google/callback")
async def google_callback(request: Request, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    if error:
        return RedirectResponse("/?auth_error=" + error)
    if state != request.cookies.get("aj_oauth_state", ""):
        raise HTTPException(400, "state mismatch")
    async with httpx.AsyncClient(timeout=20) as c:
        tr = await c.post(GOOGLE_TOKEN, data={"code": code, "client_id": settings.GOOGLE_CLIENT_ID,
                                              "client_secret": settings.GOOGLE_CLIENT_SECRET,
                                              "redirect_uri": settings.BASE_URL + "/api/auth/google/callback",
                                              "grant_type": "authorization_code"})
        tr.raise_for_status()
        tok = tr.json()
        ui = (await c.get(GOOGLE_USERINFO, headers={"Authorization": "Bearer " + tok["access_token"]})).json()
    u = db.query(User).filter_by(email=ui["email"]).first()
    if not u:
        u = User(email=ui["email"], name=ui.get("name", ""), picture=ui.get("picture", ""), google_sub=ui.get("sub", ""))
        db.add(u)
        db.flush()
    else:
        u.google_sub = ui.get("sub", u.google_sub)
        u.picture = ui.get("picture", u.picture)
    if state.endswith("|gmail"):
        u.gmail_connected = True
        if tok.get("refresh_token"):
            u.gmail_refresh_token = tok["refresh_token"]   # prototype: stored plain; production: KMS-encrypted vault
    ensure_profile(db, u)
    resp = RedirectResponse("/app")
    set_session(resp, u.id)
    resp.delete_cookie("aj_oauth_state")
    return resp


# ---------- Demo sign-in (no Google client configured, or for stage demos) ----------
class DemoLogin(BaseModel):
    email: str
    name: str = ""


@router.post("/demo")
def demo_login(body: DemoLogin, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "enter an email")
    u = db.query(User).filter_by(email=email).first()
    if not u:
        u = User(email=email, name=body.name or email.split("@")[0].title())
        db.add(u)
        db.flush()
    ensure_profile(db, u)
    set_session(response, u.id)
    return user_out(u)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.post("/gmail/demo-connect")
def gmail_demo_connect(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Demo path when Gmail scope is not configured: marks the mailbox as connected and
    uses the forwarding-alias approach (recruiter mails forwarded to the AutoJopps inbox)."""
    u = db.get(User, user.id)
    u.gmail_connected = True
    return {"ok": True, "mode": "forwarding-alias", "alias": f"inbox+{u.id}@autojopps.example"}


@router.get("/gmail/recent")
async def gmail_recent(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lists recent recruiter-looking mails via Gmail API when a refresh token exists; else demo data."""
    u = db.get(User, user.id)
    if u.gmail_refresh_token and settings.google_enabled:
        async with httpx.AsyncClient(timeout=20) as c:
            tr = await c.post(GOOGLE_TOKEN, data={"client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET,
                                                  "refresh_token": u.gmail_refresh_token, "grant_type": "refresh_token"})
            if tr.status_code != 200:
                return {"mode": "gmail-api", "error": "token refresh failed", "messages": []}
            at = tr.json()["access_token"]
            q = "newer_than:30d (application OR interview OR recruiter OR shortlisted OR naukri OR linkedin)"
            lr = await c.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", params={"q": q, "maxResults": 10},
                             headers={"Authorization": "Bearer " + at})
            out = []
            for m in lr.json().get("messages", [])[:10]:
                mr = await c.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}", params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
                                 headers={"Authorization": "Bearer " + at})
                h = {x["name"]: x["value"] for x in mr.json().get("payload", {}).get("headers", [])}
                out.append({"subject": h.get("Subject", ""), "from": h.get("From", ""), "date": h.get("Date", "")})
            return {"mode": "gmail-api", "messages": out}
    return {"mode": "demo", "messages": [
        {"subject": "Your application for Senior Backend Engineer was viewed", "from": "Naukri <noreply@naukri.example>", "date": "today"},
        {"subject": "Interview invite: Platform Architect", "from": "Talent team <talent@acme.example>", "date": "yesterday"},
    ]}
