"""Notification service: in-app always; email via SMTP and WhatsApp via Meta Cloud API when configured and consented."""
import smtplib
from email.message import EmailMessage

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .auth import current_user
from .config import settings
from .db import get_db, User, Notification, Profile

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _email(to: str, subject: str, body: str) -> str:
    if not settings.smtp_enabled:
        return "logged"
    try:
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = settings.SMTP_FROM, to, subject
        m.set_content(body)
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
            s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.send_message(m)
        return "sent"
    except Exception as e:
        return "failed:" + str(e)[:80]


def _whatsapp(to: str, title: str, body: str) -> str:
    if not settings.whatsapp_enabled:
        return "logged"
    try:
        url = f"https://graph.facebook.com/v20.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        # Business-initiated message outside the 24h window must be a template (utility category).
        payload = {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "template",
                   "template": {"name": settings.WHATSAPP_TEMPLATE_NAME, "language": {"code": "en"},
                                "components": [{"type": "body", "parameters": [{"type": "text", "text": title}, {"type": "text", "text": body[:200]}]}]}}
        r = httpx.post(url, json=payload, headers={"Authorization": "Bearer " + settings.WHATSAPP_TOKEN}, timeout=15)
        return "sent" if r.status_code < 300 else "failed:" + r.text[:80]
    except Exception as e:
        return "failed:" + str(e)[:80]


def notify(db: Session, user_id: int, kind: str, title: str, body: str = "", application_id=None, channels=("in_app", "email", "whatsapp")):
    """Writes an in-app notification and fans out to consented external channels."""
    p = db.query(Profile).filter_by(user_id=user_id).first()
    n = Notification(user_id=user_id, channel="in_app", kind=kind, title=title, body=body, application_id=application_id, delivered="in_app")
    db.add(n)
    nf = (p.notify if p else {}) or {}
    if "email" in channels and nf.get("email_consent") and nf.get("email"):
        db.add(Notification(user_id=user_id, channel="email", kind=kind, title=title, body=body, application_id=application_id,
                            delivered=_email(nf["email"], "[AutoJopps] " + title, body)))
    if "whatsapp" in channels and nf.get("whatsapp_consent") and nf.get("whatsapp"):
        db.add(Notification(user_id=user_id, channel="whatsapp", kind=kind, title=title, body=body, application_id=application_id,
                            delivered=_whatsapp(nf["whatsapp"], title, body)))
    db.flush()
    return n


@router.get("")
def list_notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Notification).filter_by(user_id=user.id).order_by(Notification.id.desc()).limit(60).all()
    return [{"id": n.id, "channel": n.channel, "kind": n.kind, "title": n.title, "body": n.body, "application_id": n.application_id,
             "delivered": n.delivered, "read": n.read, "at": n.created_at.isoformat() + "Z"} for n in rows]


@router.post("/read-all")
def read_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter_by(user_id=user.id, read=False).update({"read": True})
    return {"ok": True}
