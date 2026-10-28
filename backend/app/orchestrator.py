"""Orchestrator: discovers jobs, scores them, enforces caps, runs one application at a time per user,
and polls portal status (viewed / in process / decision). Runs as a background thread."""
import threading
import time
from datetime import datetime

import httpx

from .ai import match_score, ask_json
from .billing import can_apply, active_sub
from .config import settings, PLANS
from .db import session, User, Job, Application, Profile
from .runner import run_application, LIVE

RUNNING = {}  # user_id -> thread
LOCK = threading.Lock()
MIN_SCORE = 25.0


def sync_jobs(db):
    try:
        r = httpx.get(settings.BASE_URL + "/portal/api/jobs", timeout=10).json()
    except Exception:
        return 0
    n = 0
    for j in r["jobs"]:
        if not db.query(Job).filter_by(portal=r["portal"], external_id=j["external_id"]).first():
            db.add(Job(portal=r["portal"], **{k: v for k, v in j.items()}))
            n += 1
    return n


def tailor(job, profile, prefs):
    base = {"headline": profile.get("headline") or profile.get("current_designation") or "Experienced professional",
            "summary": f"I bring {prefs.get('experience_years') or profile.get('total_experience_years') or ''} years of experience across "
                       f"{', '.join((prefs.get('skills') or profile.get('skills') or [])[:4])}, which maps directly to the {job.title} role at {job.company}."}
    data, used = ask_json("Write a 2-sentence cover note and a 10-word headline for this job from the profile. Return JSON {headline, summary}. No claims not in the profile.",
                          f"Job: {job.title} at {job.company}. {job.description}\nProfile: {profile}\nPreferences: {prefs}", 300)
    if used and data and data.get("summary"):
        return {"headline": data.get("headline", base["headline"]), "summary": data["summary"], "by": "claude"}
    return {**base, "by": "template"}


def match_user(db, user):
    prof = db.query(Profile).filter_by(user_id=user.id).first()
    if not prof or not prof.target_jds:
        return 0
    existing = {a.job_id for a in db.query(Application).filter_by(user_id=user.id)}
    n = 0
    for job in db.query(Job).all():
        if job.id in existing:
            continue
        jd = {"title": job.title, "description": job.description, "skills": job.skills, "min_exp": job.min_exp, "max_exp": job.max_exp,
              "salary_max_lpa": job.salary_max_lpa, "work_mode": job.work_mode, "location": job.location}
        score, reasons, hard = match_score(jd, prof.data or {}, prof.preferences or {}, prof.target_jds or [])
        db.add(Application(user_id=user.id, job_id=job.id, state="matched" if (hard and score >= MIN_SCORE) else "skipped",
                           score=score, match_reasons=reasons + ([] if hard else ["filtered out"])))
        n += 1
    return n


def queue_next(db, user):
    ok, why = can_apply(db, user.id)
    if not ok:
        return None, why
    a = (db.query(Application).filter_by(user_id=user.id, state="matched").order_by(Application.score.desc()).first())
    if not a:
        return None, "nothing left to apply to"
    prof = db.query(Profile).filter_by(user_id=user.id).first()
    a.tailored = tailor(a.job, prof.data or {}, prof.preferences or {})
    a.history = (a.history or []) + [{"at": datetime.utcnow().isoformat() + "Z", "from": a.state, "to": "queued", "note": "cap slot reserved"}]
    a.state = "queued"
    return a.id, ""


def poll_statuses(db):
    for a in db.query(Application).filter(Application.state.in_(("submitted", "viewed", "in_process")), Application.external_ref != "").all():
        try:
            r = httpx.get(settings.BASE_URL + f"/portal/api/status/{a.external_ref}", timeout=5).json()
        except Exception:
            continue
        st = r.get("status")
        if st and st != a.state and st in ("viewed", "in_process", "shortlisted", "rejected"):
            a.history = (a.history or []) + [{"at": datetime.utcnow().isoformat() + "Z", "from": a.state, "to": st, "note": "portal status"}]
            a.state = st
            from .notify import notify
            notify(db, a.user_id, "status", f"{a.job.title} at {a.job.company}: {st.replace('_', ' ')}", "", application_id=a.id, channels=("in_app",))


def tick():
    with session() as db:
        if db.query(Job).count() == 0:
            sync_jobs(db)
        poll_statuses(db)
        for user in db.query(User).filter_by(agent_enabled=True).all():
            if not active_sub(db, user.id):
                user.agent_enabled = False
                continue
            match_user(db, user)
            with LOCK:
                t = RUNNING.get(user.id)
                if t and t.is_alive():
                    continue
                # resume anything left queued/preparing from a previous process, else queue next
                stuck = db.query(Application).filter(Application.user_id == user.id, Application.state.in_(("queued",))).first()
                app_id = stuck.id if stuck else None
                if not app_id:
                    app_id, why = queue_next(db, user)
                if app_id:
                    db.commit()
                    th = threading.Thread(target=run_application, args=(app_id,), daemon=True)
                    RUNNING[user.id] = th
                    th.start()


def loop():
    while True:
        try:
            tick()
        except Exception as e:  # keep the loop alive
            print("orchestrator error:", e)
        time.sleep(settings.TICK)


def start():
    with session() as db:
        for a in db.query(Application).filter(Application.state.in_(("preparing", "submitting", "needs_human", "awaiting_approval"))):
            a.history = (a.history or []) + [{"at": datetime.utcnow().isoformat() + "Z", "from": a.state, "to": "failed", "note": "process restarted"}]
            a.state = "failed"
            a.hitl = {}
    threading.Thread(target=loop, daemon=True).start()


def run_one_now(user_id, application_id):
    with LOCK:
        t = RUNNING.get(user_id)
        if t and t.is_alive():
            return False, "a run is already in progress"
        th = threading.Thread(target=run_application, args=(application_id,), daemon=True)
        RUNNING[user_id] = th
        th.start()
        return True, ""
