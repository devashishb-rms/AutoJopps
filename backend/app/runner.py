"""Browser runner. One thread per run; Playwright (sync API) lives entirely inside that thread.
While an application waits for a human, the thread pumps commands (screenshot, click, type, key) coming from
the live-view websocket, so the human can see and drive the exact browser the bot is using.

Skills: a list of steps for a portal. Each target has several locators (id, label, name). If the preferred one
fails, the runner falls back to the next, logs a 'repair', and files a trial skill version (self-heal)."""
import base64
import json
import queue
import re
import threading
import time
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path

from .ai import draft_answer
from .config import settings, ROOT
from .db import session, Application, Job, Profile, User, Resume, AnswerMemory, Skill, Recording, RunLog
from .notify import notify

VAULT = ROOT / "data" / "vault"
VAULT.mkdir(parents=True, exist_ok=True)
LIVE = {}  # application_id -> LiveSession
HITL_TIMEOUT = 20 * 60


class LiveSession:
    def __init__(self, app_id):
        self.app_id = app_id
        self.cmds = queue.Queue()
        self.viewers = 0
        self.recording = []
        self.record = False

    def call(self, name, *args, timeout=20):
        fut = Future()
        self.cmds.put((name, args, fut))
        return fut.result(timeout)


def log(app_id, msg, level="info"):
    with session() as db:
        db.add(RunLog(application_id=app_id, level=level, message=msg))


def transition(app_id, to, note=""):
    with session() as db:
        a = db.get(Application, app_id)
        a.history = (a.history or []) + [{"at": datetime.utcnow().isoformat() + "Z", "from": a.state, "to": to, "note": note}]
        a.state = to
        if to == "submitted":
            a.submitted_at = datetime.utcnow()
        return a.user_id


BUILTIN_STEPS = [
    {"action": "fill", "target": {"id": "f_name", "label": "Full name", "name": "name"}, "value": "profile.name"},
    {"action": "fill", "target": {"id": "f_phone", "label": "Mobile", "name": "phone"}, "value": "profile.phone"},
    {"action": "fill", "target": {"id": "f_exp", "label": "Total experience (years)", "name": "exp"}, "value": "profile.total_experience_years"},
    {"action": "fill", "target": {"id": "f_ctc", "label": "Current CTC (LPA)", "name": "ctc"}, "value": "profile.current_ctc_lpa"},
    {"action": "fill", "target": {"id": "f_notice", "label": "Notice period (days)", "name": "notice"}, "value": "profile.notice_period_days"},
    {"action": "fill", "target": {"id": "f_headline", "label": "Headline", "name": "headline"}, "value": "tailored.headline"},
    {"action": "fill", "target": {"id": "f_summary", "label": "Why are you a fit? (cover note)", "name": "summary"}, "value": "tailored.summary"},
    {"action": "upload", "target": {"id": "f_resume", "label": "Resume (PDF/DOCX)", "name": "resume"}, "value": "resume.path"},
    {"action": "questions", "target": {"css": "input[data-question]"}},
    {"action": "click", "target": {"id": "continue-btn", "text": "Continue"}},
]


def ensure_builtin_skill(portal):
    with session() as db:
        s = db.query(Skill).filter_by(portal=portal, status="active").order_by(Skill.version.desc()).first()
        if not s:
            s = Skill(portal=portal, version=1, status="active", steps=BUILTIN_STEPS, origin="built-in")
            db.add(s)
            db.flush()
        return s.id, s.version, s.steps


def locate(page, target, app_id, repairs):
    """Try locators in order: id, name, label, css, text. Record a repair when the first choice failed."""
    tried = []
    order = [("id", lambda v: page.locator("#" + v)), ("name", lambda v: page.locator(f"[name='{v}']")),
             ("label", lambda v: page.get_by_label(v, exact=False)), ("css", lambda v: page.locator(v)),
             ("text", lambda v: page.get_by_role("button", name=v))]
    for i, (k, mk) in enumerate(order):
        v = target.get(k)
        if not v:
            continue
        loc = mk(v)
        try:
            if loc.count() > 0:
                if tried:
                    repairs.append({"target": target, "used": k, "failed": tried})
                    log(app_id, f"self-heal: '{tried[0]}' not found, used {k}='{v}'", "warn")
                return loc.first
        except Exception:
            pass
        tried.append(f"{k}={v}")
    return None


def resolve_value(expr, ctx):
    root, _, key = expr.partition(".")
    v = ctx.get(root, {})
    v = v.get(key, "") if isinstance(v, dict) else v
    return "" if v is None else str(v)


def normalize_q(q):
    return re.sub(r"[^a-z0-9 ]", "", q.lower()).strip()


def lookup_answer(db, user_id, question):
    nq = normalize_q(question)
    rows = db.query(AnswerMemory).filter_by(user_id=user_id).all()
    best, score = None, 0.0
    for r in rows:
        a, b = set(nq.split()), set(r.normalized.split())
        s = len(a & b) / max(1, len(a | b))
        if s > score:
            best, score = r, s
    if best and score >= 0.6 and best.confirmed:
        best.uses += 1
        return best.answer, score
    return None, score


def wait_for_human(app_id, live, page, kind, payload):
    """Sets needs_human, notifies, then pumps live-view commands until the app has a response or times out."""
    with session() as db:
        a = db.get(Application, app_id)
        a.hitl = {"kind": kind, **payload, "created_at": datetime.utcnow().isoformat() + "Z"}
        a.hitl_response = {}
        uid, title = a.user_id, a.job.title
    transition(app_id, "needs_human" if kind != "approve" else "awaiting_approval", f"{kind}: {payload.get('question', '')}")
    with session() as db:
        msg = {"login": "Please sign in to the portal (one time) in the live view.", "otp": "An OTP is needed to continue.",
               "captcha": "A human check needs your input.", "question": "A screening question needs your answer: " + payload.get("question", ""),
               "approve": "Ready to submit. Approve to continue."}[kind]
        notify(db, uid, "hitl", f"Help needed: {title}", msg, application_id=app_id)
    log(app_id, f"waiting for human: {kind}")
    t0 = time.time()
    last_check = 0.0
    while time.time() - t0 < HITL_TIMEOUT:
        try:
            name, args, fut = live.cmds.get(timeout=0.5)
        except queue.Empty:
            name = None
        if name:
            try:
                fut.set_result(exec_cmd(page, live, name, args))
            except Exception as e:
                fut.set_exception(e)
        if time.time() - last_check < 0.8:
            continue
        last_check = time.time()
        with session() as db:
            a = db.get(Application, app_id)
            if a.hitl_response:
                r = dict(a.hitl_response)
                a.hitl = {}
                return r
            if a.state in ("skipped", "failed"):
                return {"action": "abort"}
    return {"action": "timeout"}


def exec_cmd(page, live, name, args):
    if name == "screenshot":
        return base64.b64encode(page.screenshot(type="jpeg", quality=60)).decode()
    if name == "size":
        return page.viewport_size
    if name == "click":
        x, y = args
        if live.record:
            sel = page.evaluate("""([x,y])=>{const e=document.elementFromPoint(x,y);if(!e)return null;
                return {id:e.id||null,name:e.getAttribute('name'),tag:e.tagName.toLowerCase(),text:(e.innerText||'').slice(0,40),
                label:(e.labels&&e.labels[0]?e.labels[0].innerText:null)}}""", [x, y])
            live.recording.append({"type": "click", "x": x, "y": y, "target": sel, "at": time.time()})
        page.mouse.click(x, y)
        return True
    if name == "type":
        (text,) = args
        if live.record:
            sel = page.evaluate("""()=>{const e=document.activeElement;if(!e)return null;return {id:e.id||null,name:e.getAttribute('name'),
                tag:e.tagName.toLowerCase(),type:e.getAttribute('type'),label:(e.labels&&e.labels[0]?e.labels[0].innerText:null)}}""")
            masked = "•" * len(text) if (sel or {}).get("type") == "password" else text
            live.recording.append({"type": "type", "target": sel, "value": masked, "at": time.time()})
        page.keyboard.type(text, delay=20)
        return True
    if name == "key":
        (k,) = args
        if live.record:
            live.recording.append({"type": "key", "key": k, "at": time.time()})
        page.keyboard.press(k)
        return True
    if name == "fill":
        selector, value = args
        page.fill(selector, value)
        return True
    if name == "record":
        (on,) = args
        live.record = bool(on)
        return live.record
    if name == "url":
        return page.url
    raise ValueError("unknown command " + name)


def run_application(app_id):
    """Full lifecycle for one application on the mock portal (or any portal with a skill)."""
    from playwright.sync_api import sync_playwright
    live = LiveSession(app_id)
    LIVE[app_id] = live
    repairs = []
    try:
        with session() as db:
            a = db.get(Application, app_id)
            job = a.job
            user = db.get(User, a.user_id)
            prof = db.query(Profile).filter_by(user_id=user.id).first()
            res = db.query(Resume).filter_by(user_id=user.id).order_by(Resume.id.desc()).first()
            ctx = {"profile": dict(prof.data or {}), "prefs": dict(prof.preferences or {}), "tailored": dict(a.tailored or {}),
                   "resume": {"path": res.path if res else ""}, "user_id": user.id, "email": user.email, "approval_mode": user.approval_mode,
                   "job": {"id": job.id, "title": job.title, "company": job.company, "url": job.url, "portal": job.portal, "external_id": job.external_id}}
        portal = ctx["job"]["portal"]
        skill_id, skill_version, steps = ensure_builtin_skill(portal)
        transition(app_id, "preparing")
        log(app_id, f"skill {portal} v{skill_version}; launching browser")
        vault_file = VAULT / f"u{ctx['user_id']}_{portal}.json"
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=settings.RUNNER_HEADLESS, slow_mo=settings.RUNNER_SLOWMO_MS)
            context = browser.new_context(viewport={"width": 1100, "height": 760},
                                          storage_state=str(vault_file) if vault_file.exists() else None)
            page = context.new_page()
            page.goto(settings.BASE_URL + ctx["job"]["url"], wait_until="domcontentloaded")
            page.click("#apply-btn")
            page.wait_for_load_state("domcontentloaded")
            # ---- login (human, one time) ----
            if "/portal/login" in page.url:
                log(app_id, "portal session missing: asking the user to sign in once")
                r = wait_for_human(app_id, live, page, "login", {"hint": "Sign in on the live view. Your password is never stored; only the portal session is."})
                if r.get("action") in ("abort", "timeout"):
                    raise RuntimeError("login not completed")
                transition(app_id, "submitting", "signed in")
            if "/portal/otp" in page.url:
                for attempt in range(3):
                    r = wait_for_human(app_id, live, page, "otp", {"hint": "Enter the 4-digit OTP from your phone."})
                    if r.get("action") in ("abort", "timeout"):
                        raise RuntimeError("otp not provided")
                    page.fill("#otp", str(r.get("value", "")).strip())
                    page.click("#otp-btn")
                    page.wait_for_load_state("domcontentloaded")
                    if "/portal/otp" not in page.url:
                        break
                    log(app_id, "OTP rejected, asking again", "warn")
                    page.goto(settings.BASE_URL + "/portal/otp", wait_until="domcontentloaded")
                transition(app_id, "submitting", "otp verified")
                context.storage_state(path=str(vault_file))
                log(app_id, "portal session saved to vault (prototype: plain file; production: KMS-encrypted)")
            if live.recording:
                with session() as db:
                    db.add(Recording(user_id=ctx["user_id"], application_id=app_id, portal=portal, events=live.recording, consent=True))
                log(app_id, f"recorded {len(live.recording)} demonstration events for learning")
            if "/form" not in page.url:
                page.goto(settings.BASE_URL + ctx["job"]["url"] + "/form", wait_until="domcontentloaded")
            transition(app_id, "submitting", "filling form")
            # ---- replay skill ----
            for st in steps:
                act = st["action"]
                if act == "fill":
                    loc = locate(page, st["target"], app_id, repairs)
                    if loc is None:
                        log(app_id, f"could not find {st['target']}", "warn")
                        continue
                    loc.fill(resolve_value(st["value"], ctx))
                elif act == "upload":
                    loc = locate(page, st["target"], app_id, repairs)
                    p = resolve_value(st["value"], ctx)
                    if loc is not None and p and Path(p).exists():
                        loc.set_input_files(p)
                elif act == "questions":
                    for q in page.locator(st["target"]["css"]).all():
                        question = q.get_attribute("data-question") or ""
                        with session() as db:
                            ans, sc = lookup_answer(db, ctx["user_id"], question)
                        source = "memory"
                        if ans is None:
                            ans, source, confident = draft_answer(question, ctx["profile"], ctx["prefs"])
                            if not confident or not ans:
                                r = wait_for_human(app_id, live, page, "question", {"question": question, "suggestion": ans, "source": source})
                                if r.get("action") in ("abort", "timeout"):
                                    raise RuntimeError("question unanswered")
                                ans, source = str(r.get("value", "")), "user"
                                transition(app_id, "submitting", "answer received")
                            with session() as db:
                                db.add(AnswerMemory(user_id=ctx["user_id"], question=question, normalized=normalize_q(question), answer=ans,
                                                    source=source, confirmed=True))
                        log(app_id, f"Q: {question[:60]} -> {ans[:40]} ({source})")
                        q.fill(ans)
                elif act == "click":
                    loc = locate(page, st["target"], app_id, repairs)
                    if loc is None:
                        raise RuntimeError("button not found: " + json.dumps(st["target"]))
                    loc.click()
                    page.wait_for_load_state("domcontentloaded")
            # ---- human check ----
            if "/portal/check" in page.url:
                for attempt in range(3):
                    r = wait_for_human(app_id, live, page, "captcha", {"hint": "Type the word shown in the live view."})
                    if r.get("action") in ("abort", "timeout"):
                        raise RuntimeError("human check not completed")
                    page.fill("#captcha", str(r.get("value", "")).strip())
                    if ctx["approval_mode"] == "approve_each":
                        r2 = wait_for_human(app_id, live, page, "approve", {"hint": "Approve to submit this application."})
                        if r2.get("action") != "approve":
                            transition(app_id, "skipped", "not approved")
                            return
                    transition(app_id, "submitting", "submitting")
                    page.click("#check-btn")
                    page.wait_for_load_state("domcontentloaded")
                    if page.locator("#app-ref").count():
                        break
                    log(app_id, "human check rejected, asking again", "warn")
                    page.goto(settings.BASE_URL + "/portal/check", wait_until="domcontentloaded")
            ref = page.locator("#app-ref").inner_text() if page.locator("#app-ref").count() else ""
            if not ref:
                raise RuntimeError("no confirmation found at " + page.url)
            proof = settings.SHOT_DIR / f"app{app_id}.png"
            page.screenshot(path=str(proof), full_page=True)
            with session() as db:
                a = db.get(Application, app_id)
                a.external_ref = ref
                a.proof_path = str(proof)
                a.cost_inr = round(0.4 + 0.15 * len(repairs), 2)  # prototype meter: browser-minute share + repairs; model cost added in ai.COST_LOG
                sk = db.get(Skill, skill_id)
                sk.runs += 1
                sk.successes += 1
                sk.repairs += len(repairs)
                if repairs:
                    new_steps = json.loads(json.dumps(steps))
                    for rp in repairs:
                        for s_ in new_steps:
                            if s_.get("target") == rp["target"]:
                                t = dict(s_["target"])
                                used = rp["used"]
                                s_["target"] = {used: t[used], **{k: v for k, v in t.items() if k != used}}
                    db.add(Skill(portal=portal, version=sk.version + 1, status="trial", steps=new_steps, origin="repaired"))
                    log(app_id, f"filed skill v{sk.version + 1} (trial) with {len(repairs)} repaired locator(s)")
            transition(app_id, "submitted", f"ref {ref}")
            with session() as db:
                notify(db, ctx["user_id"], "submitted", f"Applied: {ctx['job']['title']} at {ctx['job']['company']}", f"Reference {ref}", application_id=app_id, channels=("in_app", "email"))
            log(app_id, f"submitted, ref {ref}")
            context.close()
            browser.close()
    except Exception as e:
        log(app_id, "failed: " + str(e)[:200], "error")
        with session() as db:
            a = db.get(Application, app_id)
            if a.state not in ("skipped", "submitted"):
                a.hitl = {}
        transition(app_id, "failed", str(e)[:120])
    finally:
        LIVE.pop(app_id, None)
