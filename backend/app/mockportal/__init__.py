"""JobHub: a realistic mock job portal served by the prototype itself, so the runner can be demonstrated
end to end without touching real portals. It has a login with OTP, a multi-field application form,
screening questions (some unusual, to trigger human help), a human-check step, and a recruiter-status
simulation (viewed / in process / shortlisted). A 'chaos' switch renames form fields to demonstrate self-healing."""
import random
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

router = APIRouter(prefix="/portal", tags=["mock portal"])
PORTAL = "jobhub"
STATE = {"sessions": {}, "otps": {}, "applications": {}, "chaos": False, "last_otp": {}}

TITLES = ["Senior Backend Engineer", "Platform Architect", "Engineering Manager", "Head of Engineering", "Lead Data Scientist",
          "Staff Software Engineer", "Principal Engineer", "Director of Engineering", "Solutions Architect", "CTO (Series A)",
          "VP Engineering", "Senior Python Developer", "ML Engineer", "Fraud Analytics Lead", "Site Reliability Lead",
          "Full Stack Engineer", "Product Engineering Lead", "Technical Program Manager", "Data Platform Lead", "Cloud Architect"]
COMPANIES = ["Acme Fintech", "Nimbus Labs", "Kaveri Systems", "Orbital Pay", "Saffron AI", "BlueTusk", "Meridian Health", "Zypher Commerce",
             "Indus Analytics", "Pivotal Cloud", "Lotus Robotics", "Vanta Logistics", "Helix Bio", "Nova EdTech", "Quanta Energy",
             "Trident Security", "Ember Media", "Argo Mobility", "Sitara Retail", "Keel Infra"]
LOCS = ["Bengaluru", "Gurugram", "Noida", "Hyderabad", "Pune", "Mumbai", "Chennai", "New Delhi", "Remote"]
SKILLS = ["python", "fastapi", "aws", "kubernetes", "postgres", "react", "microservices", "architecture", "leadership", "machine learning",
          "nlp", "llm", "kafka", "spark", "devops", "java", "go", "redis", "fraud", "aml", "data science", "playwright"]
QUESTIONS_STD = ["What is your notice period?", "What is your current CTC?", "What is your expected CTC?", "Total years of experience?"]
QUESTIONS_ODD = ["Are you willing to relocate to our office city?", "Have you led a team of more than 10 engineers?",
                 "Do you hold any patents or publications?", "Describe one production incident you handled and what changed after it.",
                 "Which of our products have you used?", "Are you open to a 3-month contract-to-hire arrangement?"]


def seed_jobs():
    rnd = random.Random(42)
    jobs = []
    for i in range(24):
        t, c = TITLES[i % len(TITLES)], COMPANIES[i % len(COMPANIES)]
        mn = rnd.choice([3, 5, 8, 10, 12, 15])
        mx = mn + rnd.choice([4, 6, 8, 10])
        smin = rnd.choice([18, 25, 35, 45, 60, 80])
        sk = rnd.sample(SKILLS, 5)
        loc = rnd.choice(LOCS)
        wm = "remote" if loc == "Remote" else rnd.choice(["hybrid", "wfo", "hybrid"])
        desc = (f"{c} is hiring a {t}. You will own {sk[0]} and {sk[1]} systems at scale, work with {sk[2]} and {sk[3]}, "
                f"and mentor engineers. Must have {mn}+ years of experience, strong {sk[4]} skills and hands-on {sk[0]}. "
                f"Location: {loc} ({wm}). Compensation {smin}-{smin + 20} LPA.")
        jobs.append({"external_id": f"JH-{1000 + i}", "title": t, "company": c, "location": loc, "work_mode": wm, "min_exp": mn, "max_exp": mx,
                     "salary_min_lpa": smin, "salary_max_lpa": smin + 20, "skills": sk, "description": desc,
                     "questions": QUESTIONS_STD[:2] + rnd.sample(QUESTIONS_ODD, 2 if i % 3 == 0 else 1), "url": f"/portal/job/JH-{1000 + i}"})
    return jobs


JOBS = {j["external_id"]: j for j in seed_jobs()}
STYLE = """<style>body{font-family:Inter,Segoe UI,Arial,sans-serif;background:#f4f6f8;color:#1b2430;margin:0}
header{background:#1f3a5f;color:#fff;padding:14px 24px;font-weight:700;font-size:18px;display:flex;justify-content:space-between}
header span{font-weight:400;font-size:13px;opacity:.85}.wrap{max-width:860px;margin:24px auto;padding:0 16px}
.card{background:#fff;border:1px solid #dfe5ec;border-radius:10px;padding:20px 24px;margin:14px 0}
h1{font-size:22px;margin:0 0 6px}h2{font-size:17px;margin:18px 0 8px}label{display:block;font-size:13px;color:#425466;margin:10px 0 4px}
input,select,textarea{width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #c7d0da;border-radius:6px;font-size:14px}
button{background:#1f3a5f;color:#fff;border:0;border-radius:6px;padding:10px 18px;font-size:14px;cursor:pointer;margin-top:14px}
.muted{color:#6b7a8c;font-size:13px}.tag{display:inline-block;background:#e8eef5;border-radius:999px;padding:2px 9px;font-size:12px;margin:2px}
.ok{background:#e4f6ec;border:1px solid #9bd3b2;padding:10px 14px;border-radius:8px}.otp{font-size:28px;letter-spacing:6px;font-weight:700}
.captcha{font-family:Georgia,serif;font-size:30px;letter-spacing:4px;background:repeating-linear-gradient(45deg,#eef,#eef 6px,#dde 6px,#dde 12px);display:inline-block;padding:8px 18px;border-radius:6px;transform:skewX(-8deg)}
a{color:#1f3a5f}.row{display:flex;gap:16px}.row>div{flex:1}</style>"""


def page(title, body, user=None):
    who = f"<span>Signed in as {user}</span>" if user else "<span>Not signed in</span>"
    return HTMLResponse(f"<!doctype html><html><head><meta charset='utf-8'><title>{title} · JobHub</title>{STYLE}</head>"
                        f"<body><header><div>JobHub <span style='font-size:12px'>(mock job portal, part of the AutoJopps prototype)</span></div>{who}</header><div class='wrap'>{body}</div></body></html>")


def sess(request: Request):
    return STATE["sessions"].get(request.cookies.get("jh_session", ""))


@router.get("/api/jobs")
def api_jobs():
    return {"portal": PORTAL, "jobs": [{k: v for k, v in j.items() if k != "questions"} for j in JOBS.values()]}


@router.get("/api/status/{ref}")
def api_status(ref: str):
    a = STATE["applications"].get(ref)
    if not a:
        return JSONResponse({"error": "unknown"}, 404)
    # recruiter simulation: viewed after ~1 min, in process after ~3, decision after ~6 (prototype speeds)
    age = (datetime.utcnow() - a["at"]).total_seconds()
    st = "submitted"
    if age > 45:
        st = "viewed"
    if age > 150:
        st = "in_process"
    if age > 330:
        st = a["decision"]
    return {"ref": ref, "status": st, "job": a["job"], "at": a["at"].isoformat()}


@router.get("/_demo/last-otp")
def last_otp(email: str = ""):
    """Simulates the user's phone for demos: returns the last OTP the portal 'sent' to this email."""
    return {"email": email, "otp": STATE["last_otp"].get(email.lower())}


@router.get("/_demo/last-check")
def last_check(email: str = ""):
    """Demo helper used only by automated tests: the current human-check word for this email."""
    for k, v in STATE["otps"].items():
        if k.startswith("cap_") and v.get("email") == email.lower():
            return {"word": v["word"]}
    return {"word": None}


@router.post("/_demo/chaos")
def chaos(on: int = 1):
    STATE["chaos"] = bool(on)
    return {"chaos": STATE["chaos"]}


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    s = sess(request)
    items = "".join(f"<div class='card'><h2 style='margin:0'><a href='/portal/job/{j['external_id']}'>{j['title']}</a></h2>"
                    f"<div class='muted'>{j['company']} · {j['location']} · {j['work_mode']} · {j['min_exp']}-{j['max_exp']} yrs · {j['salary_min_lpa']}-{j['salary_max_lpa']} LPA</div>"
                    f"<div>{''.join(f'<span class=tag>{s_}</span>' for s_ in j['skills'])}</div></div>" for j in JOBS.values())
    return page("Jobs", f"<h1>Open roles</h1><p class='muted'>{len(JOBS)} jobs. Sign in to apply.</p>{items}", s and s["email"])


@router.get("/job/{jid}", response_class=HTMLResponse)
def job(request: Request, jid: str):
    j = JOBS.get(jid)
    if not j:
        return page("Not found", "<h1>Job not found</h1>")
    s = sess(request)
    return page(j["title"], f"<div class='card'><h1 id='job-title'>{j['title']}</h1><div class='muted'>{j['company']} · {j['location']} · {j['work_mode']}</div>"
                f"<p>{j['description']}</p><div>{''.join(f'<span class=tag>{s_}</span>' for s_ in j['skills'])}</div>"
                f"<form method='post' action='/portal/job/{jid}/apply'><button id='apply-btn' type='submit'>Apply now</button></form></div>", s and s["email"])


@router.post("/job/{jid}/apply")
def apply_start(request: Request, jid: str):
    s = sess(request)
    if not s:
        return RedirectResponse(f"/portal/login?next=/portal/job/{jid}/apply", 303)
    return RedirectResponse(f"/portal/job/{jid}/form", 303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/portal/"):
    return page("Sign in", f"<div class='card'><h1>Sign in to JobHub</h1><p class='muted'>Use any email. Password for this mock portal is <b>demo</b>. An OTP will follow.</p>"
                f"<form method='post' action='/portal/login'><input type='hidden' name='next' value='{next}'>"
                f"<label>Email</label><input id='email' name='email' type='email' required>"
                f"<label>Password</label><input id='password' name='password' type='password' required>"
                f"<button id='login-btn' type='submit'>Continue</button></form></div>")


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/portal/")):
    if password != "demo":
        return page("Sign in", "<div class='card'><h1>Wrong password</h1><p>The mock portal password is <b>demo</b>. <a href='/portal/login'>Try again</a></p></div>")
    otp = f"{random.randint(1000, 9999)}"
    tok = secrets.token_urlsafe(12)
    STATE["otps"][tok] = {"email": email.lower(), "otp": otp, "next": next}
    STATE["last_otp"][email.lower()] = otp
    resp = RedirectResponse("/portal/otp", 303)
    resp.set_cookie("jh_otp", tok, httponly=True)
    return resp


@router.get("/otp", response_class=HTMLResponse)
def otp_page(request: Request):
    t = STATE["otps"].get(request.cookies.get("jh_otp", ""))
    if not t:
        return RedirectResponse("/portal/login", 303)
    return page("Verify OTP", f"<div class='card'><h1>Enter the OTP</h1><p class='muted'>We sent a 4-digit code to the mobile number linked to {t['email']}.</p>"
                f"<form method='post' action='/portal/otp'><label>OTP</label><input id='otp' name='otp' maxlength='4' pattern='\\d{{4}}' required autofocus>"
                f"<button id='otp-btn' type='submit'>Verify</button></form></div>")


@router.post("/otp")
def otp_submit(request: Request, otp: str = Form(...)):
    tok = request.cookies.get("jh_otp", "")
    t = STATE["otps"].get(tok)
    if not t or t["otp"] != otp.strip():
        return page("Verify OTP", "<div class='card'><h1 id='otp-error'>Incorrect OTP</h1><p><a href='/portal/otp'>Try again</a></p></div>")
    sid = secrets.token_urlsafe(16)
    STATE["sessions"][sid] = {"email": t["email"], "at": datetime.utcnow()}
    resp = RedirectResponse(t["next"], 303)
    resp.set_cookie("jh_session", sid, httponly=True, max_age=7 * 86400)
    resp.delete_cookie("jh_otp")
    STATE["otps"].pop(tok, None)
    return resp


def fid(name):
    """Field id; with chaos on, ids are renamed to show self-healing by label."""
    return f"f_{name}_x" if STATE["chaos"] else f"f_{name}"


@router.get("/job/{jid}/form", response_class=HTMLResponse)
def form_page(request: Request, jid: str):
    s = sess(request)
    j = JOBS.get(jid)
    if not s:
        return RedirectResponse(f"/portal/login?next=/portal/job/{jid}/apply", 303)
    qs = "".join(f"<label for='q{i}'>{q}</label><input id='q{i}' name='q{i}' data-question='{q}' required>" for i, q in enumerate(j["questions"]))
    body = (f"<div class='card'><h1>Apply: {j['title']} at {j['company']}</h1><form id='apply-form' method='post' action='/portal/job/{jid}/submit' enctype='multipart/form-data'>"
            f"<div class='row'><div><label for='{fid('name')}'>Full name</label><input id='{fid('name')}' name='name' required></div>"
            f"<div><label for='{fid('email')}'>Email</label><input id='{fid('email')}' name='email' type='email' value='{s['email']}' required></div></div>"
            f"<div class='row'><div><label for='{fid('phone')}'>Mobile</label><input id='{fid('phone')}' name='phone' required></div>"
            f"<div><label for='{fid('exp')}'>Total experience (years)</label><input id='{fid('exp')}' name='exp' type='number' step='0.5' required></div></div>"
            f"<div class='row'><div><label for='{fid('ctc')}'>Current CTC (LPA)</label><input id='{fid('ctc')}' name='ctc' type='number' step='0.1' required></div>"
            f"<div><label for='{fid('notice')}'>Notice period (days)</label><input id='{fid('notice')}' name='notice' type='number' required></div></div>"
            f"<label for='{fid('headline')}'>Headline</label><input id='{fid('headline')}' name='headline'>"
            f"<label for='{fid('summary')}'>Why are you a fit? (cover note)</label><textarea id='{fid('summary')}' name='summary' rows='4'></textarea>"
            f"<label for='{fid('resume')}'>Resume (PDF/DOCX)</label><input id='{fid('resume')}' name='resume' type='file'>"
            f"<h2>Screening questions</h2>{qs}"
            f"<button id='continue-btn' type='submit'>Continue</button></form></div>")
    return page("Apply", body, s["email"])


@router.post("/job/{jid}/submit")
async def form_submit(request: Request, jid: str, resume: UploadFile = File(None)):
    s = sess(request)
    if not s:
        return RedirectResponse("/portal/login", 303)
    form = await request.form()
    data = {k: v for k, v in form.items() if k != "resume"}
    data["resume_name"] = resume.filename if resume else ""
    word = random.choice(["harbor", "meadow", "copper", "lantern", "velvet", "summit"])
    tok = secrets.token_urlsafe(8)
    STATE["otps"]["cap_" + tok] = {"word": word, "jid": jid, "data": data, "email": s["email"]}
    resp = RedirectResponse("/portal/check", 303)
    resp.set_cookie("jh_check", tok, httponly=True)
    return resp


@router.get("/check", response_class=HTMLResponse)
def check_page(request: Request):
    t = STATE["otps"].get("cap_" + request.cookies.get("jh_check", ""))
    if not t:
        return RedirectResponse("/portal/", 303)
    return page("Human check", f"<div class='card'><h1>Quick human check</h1><p class='muted'>Type the word shown below. (This stands in for a CAPTCHA.)</p>"
                f"<div class='captcha' id='captcha-word' aria-label='captcha'>{t['word']}</div>"
                f"<form method='post' action='/portal/check'><label>Word</label><input id='captcha' name='captcha' required autofocus>"
                f"<button id='check-btn' type='submit'>Submit application</button></form></div>", t["email"])


@router.post("/check")
def check_submit(request: Request, captcha: str = Form(...)):
    key = "cap_" + request.cookies.get("jh_check", "")
    t = STATE["otps"].get(key)
    if not t:
        return RedirectResponse("/portal/", 303)
    if captcha.strip().lower() != t["word"]:
        return page("Human check", "<div class='card'><h1 id='check-error'>That did not match</h1><p><a href='/portal/check'>Try again</a></p></div>")
    ref = "APP-" + secrets.token_hex(3).upper()
    STATE["applications"][ref] = {"job": t["jid"], "email": t["email"], "data": t["data"], "at": datetime.utcnow(),
                                  "decision": random.choice(["shortlisted", "rejected", "shortlisted", "in_process"])}
    STATE["otps"].pop(key, None)
    j = JOBS[t["jid"]]
    resp = page("Submitted", f"<div class='card'><div class='ok'><h1 id='confirm-title'>Application submitted</h1>"
                             f"<p>Reference <b id='app-ref'>{ref}</b> · {j['title']} at {j['company']}</p><p class='muted'>The recruiter will review your application. You can track its status on JobHub.</p></div>"
                             f"<p><a href='/portal/'>Back to jobs</a></p></div>", t["email"])
    resp.delete_cookie("jh_check")
    return resp
