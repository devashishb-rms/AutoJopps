"""Agent control, HITL responses, live view (websocket), tracking, learning loop, admin stats."""
import asyncio
import json
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import orchestrator
from .ai import COST_LOG
from .auth import current_user, signer, COOKIE
from .billing import active_sub, usage
from .config import settings, PLANS
from .db import get_db, session, User, Job, Application, RunLog, AnswerMemory, Skill, Recording, Notification, Subscription
from .runner import LIVE, transition, BUILTIN_STEPS

router = APIRouter(prefix="/api", tags=["agent"])


# ---------------- agent ----------------
@router.get("/agent/status")
def agent_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, user.id)
    sub = active_sub(db, u.id)
    d, m = usage(db, u.id)
    counts = dict(db.query(Application.state, func.count(Application.id)).filter_by(user_id=u.id).group_by(Application.state).all())
    active = db.query(Application).filter(Application.user_id == u.id, Application.state.in_(("preparing", "submitting", "needs_human", "awaiting_approval", "queued"))).first()
    t = orchestrator.RUNNING.get(u.id)
    return {"enabled": u.agent_enabled, "running": bool(t and t.is_alive()), "plan": sub.plan if sub else None,
            "used_today": d, "used_month": m, "counts": counts, "active_application": active.id if active else None,
            "active_state": active.state if active else None, "modes": settings.modes(), "model_cost": COST_LOG}


class ToggleBody(BaseModel):
    enabled: bool


@router.post("/agent/toggle")
def agent_toggle(body: ToggleBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = db.get(User, user.id)
    if body.enabled and not active_sub(db, u.id):
        raise HTTPException(400, "choose a plan first")
    if body.enabled and u.onboarding_step < 5:
        raise HTTPException(400, "finish onboarding first")
    u.agent_enabled = body.enabled
    if body.enabled:
        u.onboarding_step = max(u.onboarding_step, 7)
    return {"enabled": u.agent_enabled}


@router.post("/agent/discover")
def discover(user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = orchestrator.sync_jobs(db)
    m = orchestrator.match_user(db, db.get(User, user.id))
    return {"new_jobs": n, "scored": m}


@router.post("/agent/apply/{application_id}")
def apply_now(application_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Application, application_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404)
    if a.state not in ("matched", "skipped", "failed"):
        raise HTTPException(400, f"cannot start from state {a.state}")
    from .billing import can_apply
    ok, why = can_apply(db, user.id)
    if not ok:
        raise HTTPException(400, why)
    from .orchestrator import tailor
    from .db import Profile
    prof = db.query(Profile).filter_by(user_id=user.id).first()
    a.tailored = orchestrator.tailor(a.job, prof.data or {}, prof.preferences or {})
    a.state = "queued"
    a.hitl = {}
    a.hitl_response = {}
    db.commit()
    ok, why = orchestrator.run_one_now(user.id, a.id)
    if not ok:
        raise HTTPException(409, why)
    return {"ok": True}


class HitlBody(BaseModel):
    action: str = "value"   # value | approve | skip
    value: str = ""


@router.post("/agent/hitl/{application_id}")
def hitl_respond(application_id: int, body: HitlBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Application, application_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404)
    if a.state not in ("needs_human", "awaiting_approval"):
        raise HTTPException(400, "not waiting for you")
    if body.action == "skip":
        a.history = (a.history or []) + [{"at": datetime.utcnow().isoformat() + "Z", "from": a.state, "to": "skipped", "note": "skipped by user"}]
        a.state = "skipped"
        a.hitl = {}
        return {"ok": True}
    a.hitl_response = {"action": body.action, "value": body.value, "at": datetime.utcnow().isoformat() + "Z"}
    return {"ok": True}


@router.post("/agent/hitl/{application_id}/login-done")
def hitl_login_done(application_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """User finished signing in on the live view; the runner continues from the page it is on."""
    a = db.get(Application, application_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404)
    a.hitl_response = {"action": "continue", "at": datetime.utcnow().isoformat() + "Z"}
    return {"ok": True}


@router.post("/agent/hitl/{application_id}/demo-login")
def hitl_demo_login(application_id: int, user: User = Depends(current_user)):
    """Convenience for stage demos: types the mock-portal credentials into the live browser (records the demonstration)."""
    live = LIVE.get(application_id)
    if not live:
        raise HTTPException(404, "no live browser for this application")
    live.call("record", True)
    live.call("fill", "#email", user.email)
    live.call("fill", "#password", "demo")
    live.recording.append({"type": "type", "target": {"id": "email"}, "value": user.email})
    live.recording.append({"type": "type", "target": {"id": "password", "type": "password"}, "value": "••••"})
    sz = live.call("size")
    live.call("key", "Enter")
    live.recording.append({"type": "key", "key": "Enter"})
    return {"ok": True}


@router.get("/agent/demo-phone")
def demo_phone(user: User = Depends(current_user)):
    """Simulated phone: the mock portal's last OTP for this user's email (only exists because the portal is a mock)."""
    try:
        r = httpx.get(settings.BASE_URL + "/portal/_demo/last-otp", params={"email": user.email}, timeout=5).json()
    except Exception:
        r = {"otp": None}
    return r


@router.post("/agent/chaos")
def chaos(on: int = 1, user: User = Depends(current_user)):
    httpx.post(settings.BASE_URL + "/portal/_demo/chaos", params={"on": on}, timeout=5)
    return {"chaos": bool(on)}


# ---------------- live view ----------------
@router.websocket("/live/{application_id}")
async def live_ws(ws: WebSocket, application_id: int):
    tok = ws.cookies.get(COOKIE)
    try:
        uid = signer.loads(tok, max_age=14 * 86400)["uid"]
    except Exception:
        await ws.close(code=4401)
        return
    with session() as db:
        a = db.get(Application, application_id)
        if not a or a.user_id != uid:
            await ws.close(code=4403)
            return
    await ws.accept()
    loop = asyncio.get_event_loop()

    async def frames():
        while True:
            live = LIVE.get(application_id)
            if not live:
                await ws.send_text(json.dumps({"type": "ended"}))
                return
            try:
                img = await loop.run_in_executor(None, lambda: live.call("screenshot", timeout=10))
                url = await loop.run_in_executor(None, lambda: live.call("url", timeout=5))
                await ws.send_text(json.dumps({"type": "frame", "jpeg": img, "url": url, "size": {"width": 1100, "height": 760}}))
            except Exception as e:
                await ws.send_text(json.dumps({"type": "busy", "detail": str(e)[:80]}))
            await asyncio.sleep(0.7)

    task = asyncio.create_task(frames())
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            live = LIVE.get(application_id)
            if not live:
                continue
            t = msg.get("type")
            try:
                if t == "click":
                    await loop.run_in_executor(None, lambda: live.call("click", float(msg["x"]), float(msg["y"])))
                elif t == "type":
                    await loop.run_in_executor(None, lambda: live.call("type", msg["text"]))
                elif t == "key":
                    await loop.run_in_executor(None, lambda: live.call("key", msg["key"]))
                elif t == "record":
                    await loop.run_in_executor(None, lambda: live.call("record", bool(msg.get("on"))))
            except Exception as e:
                await ws.send_text(json.dumps({"type": "error", "detail": str(e)[:120]}))
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()


# ---------------- tracking ----------------
def app_out(a: Application, with_detail=False):
    j = a.job
    o = {"id": a.id, "state": a.state, "score": a.score, "reasons": a.match_reasons, "external_ref": a.external_ref,
         "job": {"id": j.id, "title": j.title, "company": j.company, "location": j.location, "work_mode": j.work_mode, "portal": j.portal,
                 "salary": f"{j.salary_min_lpa:.0f}-{j.salary_max_lpa:.0f} LPA", "exp": f"{j.min_exp}-{j.max_exp} yrs", "url": j.url, "skills": j.skills},
         "hitl": a.hitl or {}, "created_at": a.created_at.isoformat() + "Z", "updated_at": (a.updated_at or a.created_at).isoformat() + "Z",
         "submitted_at": a.submitted_at.isoformat() + "Z" if a.submitted_at else None, "cost_inr": a.cost_inr, "has_proof": bool(a.proof_path)}
    if with_detail:
        o["history"] = a.history or []
        o["tailored"] = a.tailored or {}
        o["description"] = j.description
    return o


@router.get("/applications")
def list_apps(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Application).filter_by(user_id=user.id).order_by(Application.updated_at.desc()).all()
    counts = {}
    for a in rows:
        counts[a.state] = counts.get(a.state, 0) + 1
    funnel = {"discovered": len(rows), "matched": sum(1 for a in rows if a.state != "skipped" or a.score >= orchestrator.MIN_SCORE),
              "submitted": sum(1 for a in rows if a.state in ("submitted", "viewed", "in_process", "shortlisted", "rejected")),
              "viewed": sum(1 for a in rows if a.state in ("viewed", "in_process", "shortlisted", "rejected")),
              "in_process": sum(1 for a in rows if a.state in ("in_process", "shortlisted", "rejected")),
              "shortlisted": sum(1 for a in rows if a.state == "shortlisted")}
    return {"applications": [app_out(a) for a in rows], "counts": counts, "funnel": funnel}


@router.get("/applications/{app_id}")
def app_detail(app_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404)
    logs = db.query(RunLog).filter_by(application_id=app_id).order_by(RunLog.id).all()
    o = app_out(a, True)
    o["logs"] = [{"at": l.at.isoformat() + "Z", "level": l.level, "message": l.message} for l in logs]
    return o


@router.get("/applications/{app_id}/proof")
def app_proof(app_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if not a or a.user_id != user.id or not a.proof_path:
        raise HTTPException(404)
    return FileResponse(a.proof_path, media_type="image/png")


# ---------------- learning loop ----------------
@router.get("/learning")
def learning(user: User = Depends(current_user), db: Session = Depends(get_db)):
    answers = db.query(AnswerMemory).filter_by(user_id=user.id).order_by(AnswerMemory.id.desc()).all()
    skills = db.query(Skill).order_by(Skill.portal, Skill.version.desc()).all()
    recs = db.query(Recording).filter_by(user_id=user.id).order_by(Recording.id.desc()).all()
    return {"answers": [{"id": r.id, "question": r.question, "answer": r.answer, "source": r.source, "confirmed": r.confirmed, "uses": r.uses} for r in answers],
            "skills": [{"id": s.id, "portal": s.portal, "version": s.version, "status": s.status, "runs": s.runs, "successes": s.successes,
                        "repairs": s.repairs, "origin": s.origin, "steps": s.steps, "created_at": s.created_at.isoformat() + "Z"} for s in skills],
            "recordings": [{"id": r.id, "portal": r.portal, "application_id": r.application_id, "events": len(r.events or []), "sample": (r.events or [])[:8],
                            "distilled_skill_id": r.distilled_skill_id, "created_at": r.created_at.isoformat() + "Z"} for r in recs]}


class AnswerBody(BaseModel):
    question: str
    answer: str


@router.post("/learning/answers")
def add_answer(body: AnswerBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .runner import normalize_q
    db.add(AnswerMemory(user_id=user.id, question=body.question, normalized=normalize_q(body.question), answer=body.answer, source="user", confirmed=True))
    return {"ok": True}


@router.put("/learning/answers/{aid}")
def edit_answer(aid: int, body: AnswerBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(AnswerMemory, aid)
    if not r or r.user_id != user.id:
        raise HTTPException(404)
    r.answer = body.answer
    r.source = "user"
    r.confirmed = True
    return {"ok": True}


@router.delete("/learning/answers/{aid}")
def del_answer(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(AnswerMemory).filter_by(id=aid, user_id=user.id).delete()
    return {"ok": True}


@router.post("/learning/recordings/{rid}/distill")
def distill(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Turns a recorded demonstration into a draft skill: typed values become profile-bound fields, clicks become steps."""
    r = db.get(Recording, rid)
    if not r or r.user_id != user.id:
        raise HTTPException(404)
    steps = []
    for ev in r.events or []:
        t = ev.get("target") or {}
        if ev["type"] == "type" and t:
            key = (t.get("id") or t.get("name") or "").lower()
            bind = "secret.password" if t.get("type") == "password" or "pass" in key else ("profile.email" if "mail" in key else f"profile.{key}")
            steps.append({"action": "fill", "target": {k: v for k, v in (("id", t.get("id")), ("name", t.get("name")), ("label", t.get("label"))) if v}, "value": bind})
        elif ev["type"] == "click" and t and t.get("tag") in ("button", "a", "input"):
            steps.append({"action": "click", "target": {k: v for k, v in (("id", t.get("id")), ("text", t.get("text"))) if v}})
        elif ev["type"] == "key" and ev.get("key") == "Enter":
            steps.append({"action": "key", "key": "Enter"})
    s = Skill(portal=r.portal, version=(db.query(func.max(Skill.version)).filter_by(portal=r.portal).scalar() or 0) + 1, status="draft",
              steps=steps, origin="recorded")
    db.add(s)
    db.flush()
    r.distilled_skill_id = s.id
    return {"skill_id": s.id, "steps": steps}


class SkillStatus(BaseModel):
    status: str


@router.put("/learning/skills/{sid}")
def skill_status(sid: int, body: SkillStatus, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(Skill, sid)
    if not s or body.status not in ("draft", "trial", "active", "retired"):
        raise HTTPException(400)
    if body.status == "active":
        for o in db.query(Skill).filter_by(portal=s.portal, status="active"):
            o.status = "retired"
    s.status = body.status
    return {"ok": True}


# ---------------- admin / stats ----------------
@router.get("/admin/stats")
def admin_stats(user: User = Depends(current_user), db: Session = Depends(get_db)):
    users = db.query(User).count()
    subs = db.query(Subscription).filter_by(status="active").all()
    mrr = sum(PLANS[s.plan]["price_inr"] for s in subs if s.plan in PLANS)
    by_plan = {}
    for s in subs:
        by_plan[s.plan] = by_plan.get(s.plan, 0) + 1
    apps = dict(db.query(Application.state, func.count(Application.id)).group_by(Application.state).all())
    submitted = sum(v for k, v in apps.items() if k in ("submitted", "viewed", "in_process", "shortlisted", "rejected"))
    cost = db.query(func.sum(Application.cost_inr)).scalar() or 0
    since = datetime.utcnow() - timedelta(days=1)
    hitl = db.query(Notification).filter(Notification.kind == "hitl", Notification.channel == "in_app", Notification.created_at >= since).count()
    skills = db.query(Skill).all()
    return {"users": users, "active_subscriptions": len(subs), "by_plan": by_plan, "mrr_inr": mrr,
            "net_mrr_inr": round(mrr / 1.18 * 0.98), "applications": apps, "submitted_total": submitted,
            "browser_cost_inr": round(cost, 2), "model_cost_inr": round(COST_LOG["inr"], 2), "model_calls": COST_LOG["calls"],
            "cost_per_application_inr": round((cost + COST_LOG["inr"]) / submitted, 2) if submitted else None,
            "hitl_last_24h": hitl, "skills": [{"portal": s.portal, "version": s.version, "status": s.status, "runs": s.runs, "repairs": s.repairs} for s in skills],
            "modes": settings.modes()}
