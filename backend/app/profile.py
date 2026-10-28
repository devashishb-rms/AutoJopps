"""Resume upload + parsing, Naukri-style onboarding form, preferences, target JDs, notification consent."""
import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .ai import parse_resume
from .auth import current_user, ensure_profile
from .config import settings
from .db import get_db, User, Resume, Profile

router = APIRouter(prefix="/api/profile", tags=["profile"])


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    if ext == ".docx":
        import docx
        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    return path.read_text(errors="ignore")


@router.post("/resume")
def upload_resume(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".pdf", ".docx", ".txt", ".md"):
        raise HTTPException(400, "upload a PDF, DOCX or TXT resume")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename)
    dest = settings.UPLOAD_DIR / f"u{user.id}_{int(datetime.utcnow().timestamp())}_{safe}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    text = extract_text(dest)
    if len(text.strip()) < 40:
        raise HTTPException(400, "could not read text from that file (scanned PDF?)")
    parsed, parser = parse_resume(text)
    r = Resume(user_id=user.id, filename=file.filename, path=str(dest), text=text[:20000], parsed=parsed, parser=parser)
    db.add(r)
    p = ensure_profile(db, user)
    if not p.data:
        p.data = {k: v for k, v in parsed.items() if k != "confidence"}
        p.data["_confidence"] = parsed.get("confidence", {})
        if parsed.get("skills") and not p.preferences.get("skills"):
            p.preferences = {**p.preferences, "skills": parsed["skills"]}
    u = db.get(User, user.id)
    u.onboarding_step = max(u.onboarding_step, 1)
    return {"resume_id": r.id, "parser": parser, "parsed": parsed, "chars": len(text)}


@router.get("")
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = ensure_profile(db, user)
    r = db.query(Resume).filter_by(user_id=user.id).order_by(Resume.id.desc()).first()
    return {"data": p.data, "preferences": p.preferences, "target_jds": p.target_jds, "notify": p.notify,
            "resume": {"id": r.id, "filename": r.filename, "parser": r.parser} if r else None,
            "onboarding_step": db.get(User, user.id).onboarding_step}


class FormBody(BaseModel):
    data: dict


@router.put("/form")
def save_form(body: FormBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = ensure_profile(db, user)
    p.data = {**p.data, **body.data}
    u = db.get(User, user.id)
    u.onboarding_step = max(u.onboarding_step, 2)
    if body.data.get("name") and not u.name:
        u.name = body.data["name"]
    return {"ok": True}


class PrefsBody(BaseModel):
    preferences: dict


@router.put("/preferences")
def save_prefs(body: PrefsBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = ensure_profile(db, user)
    p.preferences = {**p.preferences, **body.preferences}
    u = db.get(User, user.id)
    u.onboarding_step = max(u.onboarding_step, 3)
    return {"ok": True}


class JDsBody(BaseModel):
    target_jds: list


@router.put("/target-jds")
def save_jds(body: JDsBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    jds = [j for j in body.target_jds if (j.get("text") or "").strip()]
    if not 1 <= len(jds) <= 3:
        raise HTTPException(400, "give 1 to 3 target job descriptions")
    p = ensure_profile(db, user)
    p.target_jds = jds
    u = db.get(User, user.id)
    u.onboarding_step = max(u.onboarding_step, 4)
    return {"ok": True}


class NotifyBody(BaseModel):
    email: str = ""
    whatsapp: str = ""
    email_consent: bool = False
    whatsapp_consent: bool = False


@router.put("/notify")
def save_notify(body: NotifyBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.whatsapp_consent and not re.fullmatch(r"\+?\d{10,15}", body.whatsapp.replace(" ", "")):
        raise HTTPException(400, "enter the WhatsApp number with country code, e.g. +919876543210")
    p = ensure_profile(db, user)
    p.notify = {"email": body.email or user.email, "whatsapp": body.whatsapp, "email_consent": body.email_consent,
                "whatsapp_consent": body.whatsapp_consent, "consent_at": datetime.utcnow().isoformat() + "Z"}
    u = db.get(User, user.id)
    u.onboarding_step = max(u.onboarding_step, 5)
    return {"ok": True}


class StepBody(BaseModel):
    step: int


@router.put("/step")
def set_step(body: StepBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, user.id)
    u.onboarding_step = max(u.onboarding_step, body.step)
    return {"onboarding_step": u.onboarding_step}


class SettingsBody(BaseModel):
    approval_mode: str | None = None


@router.put("/settings")
def set_settings(body: SettingsBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, user.id)
    if body.approval_mode in ("auto", "approve_each"):
        u.approval_mode = body.approval_mode
    return {"approval_mode": u.approval_mode}


@router.post("/delete-my-data")
def delete_my_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """DPDP erasure: removes resume files, profile, answers, recordings, applications, notifications."""
    from .db import AnswerMemory, Recording, Application, Notification, RunLog, Subscription, Payment
    for r in db.query(Resume).filter_by(user_id=user.id):
        try:
            Path(r.path).unlink(missing_ok=True)
        except Exception:
            pass
        db.delete(r)
    for model in (Profile, AnswerMemory, Recording, Application, Notification, Subscription, Payment):
        db.query(model).filter_by(user_id=user.id).delete()
    u = db.get(User, user.id)
    u.onboarding_step = 0
    u.agent_enabled = False
    u.gmail_connected = False
    u.gmail_refresh_token = ""
    return {"ok": True, "deleted": True}
