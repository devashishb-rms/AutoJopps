"""Model gateway: Claude when a key exists, deterministic heuristics otherwise. Every call is cost-metered."""
import json
import re

from .config import settings

COST_LOG = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "inr": 0.0}
# Haiku 4.5-class list prices per million tokens (USD), converted at 95.1 INR/USD. Adjust in one place.
PRICE_IN, PRICE_OUT, FX = 1.0, 5.0, 95.1


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def ask_json(system: str, prompt: str, max_tokens=1500):
    """Returns (dict_or_None, used_claude: bool)."""
    if not settings.claude_enabled:
        return None, False
    try:
        r = _client().messages.create(model=settings.ANTHROPIC_MODEL, max_tokens=max_tokens, system=system,
                                      messages=[{"role": "user", "content": prompt}])
        u = r.usage
        COST_LOG["calls"] += 1
        COST_LOG["input_tokens"] += u.input_tokens
        COST_LOG["output_tokens"] += u.output_tokens
        COST_LOG["inr"] += (u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT) / 1e6 * FX
        txt = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", txt, re.S)
        return (json.loads(m.group(0)) if m else None), True
    except Exception as e:  # noqa
        return {"_error": str(e)}, True


RESUME_SCHEMA = {
    "name": "", "email": "", "phone": "", "location": "", "headline": "", "summary": "",
    "total_experience_years": 0, "current_designation": "", "current_company": "", "current_ctc_lpa": 0,
    "notice_period_days": 0, "skills": [], "education": [{"degree": "", "institute": "", "year": ""}],
    "experience": [{"company": "", "title": "", "from": "", "to": "", "highlights": []}],
    "certifications": [], "languages": [], "confidence": {"field": 0.0},
}


def parse_resume(text: str):
    sys_p = ("You extract structured candidate data from a resume for an Indian job-portal onboarding form. "
             "Return ONLY a JSON object with this exact shape: " + json.dumps(RESUME_SCHEMA) +
             ". Use null/empty when unknown. Put a 0-1 confidence per top-level field in 'confidence'.")
    data, used = ask_json(sys_p, text[:12000], 2000)
    if used and data and "_error" not in data:
        return data, "claude"
    return heuristic_resume(text), "heuristic"


def heuristic_resume(text: str):
    d = json.loads(json.dumps(RESUME_SCHEMA))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    d["name"] = lines[0][:60] if lines else ""
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    d["email"] = m.group(0) if m else ""
    m = re.search(r"(\+91[\s-]?)?[6-9]\d{9}", text)
    d["phone"] = m.group(0) if m else ""
    m = re.search(r"(\d{1,2})\+?\s*(years|yrs)", text, re.I)
    d["total_experience_years"] = int(m.group(1)) if m else 0
    m = re.search(r"(\d{1,3})\s*days?\s*notice|notice\s*period\s*[:\-]?\s*(\d{1,3})", text, re.I)
    d["notice_period_days"] = int(m.group(1) or m.group(2)) if m else 30
    m = re.search(r"(\d{1,3}(?:\.\d)?)\s*LPA", text, re.I)
    d["current_ctc_lpa"] = float(m.group(1)) if m else 0
    known = ["python", "java", "javascript", "typescript", "react", "node", "fastapi", "django", "flask", "aws", "gcp", "azure",
             "kubernetes", "docker", "postgres", "mysql", "mongodb", "redis", "kafka", "spark", "playwright", "selenium",
             "machine learning", "deep learning", "nlp", "llm", "genai", "data science", "sql", "go", "rust", "c++", "c#",
             "microservices", "architecture", "leadership", "product management", "fraud", "aml", "fintech", "devops", "ci/cd"]
    low = text.lower()
    d["skills"] = [k for k in known if k in low][:25]
    m = re.search(r"(CTO|Chief Technology Officer|VP|Vice President|Director|Architect|Engineering Manager|Lead|Senior [A-Za-z ]+Engineer|Software Engineer|Data Scientist)[^\n,|]{0,40}", text)
    d["current_designation"] = m.group(0).strip() if m else ""
    m = re.search(r"\b(IIT|IIM|NIT|BITS|University|Institute)[^\n,]{0,60}", text)
    if m:
        d["education"] = [{"degree": "", "institute": m.group(0).strip(), "year": ""}]
    d["headline"] = d["current_designation"] or (d["skills"][0].title() + " professional" if d["skills"] else "")
    d["summary"] = " ".join(lines[1:4])[:300]
    for k in ("name", "email", "phone", "skills", "total_experience_years"):
        d["confidence"][k] = 0.6 if d.get(k) else 0.1
    d["confidence"]["_parser"] = "heuristic"
    return d


def tokenize(s: str):
    return set(w for w in re.findall(r"[a-z0-9+#.]{2,}", (s or "").lower()) if w not in STOP)


STOP = set("the and for with that this from are will you our your have has was were been can all any into over under per about more than not but or as at by on in of to a an is it be we they them their its".split())


def match_score(job, profile_data, prefs, target_jds):
    """0-100 score with reasons. Keyword overlap with target JDs + hard filters from preferences."""
    reasons = []
    jt = tokenize(job["title"] + " " + job["description"] + " " + " ".join(job.get("skills", [])))
    skills = set(s.lower() for s in (prefs.get("skills") or profile_data.get("skills") or []))
    sk_hit = skills & jt
    s_skill = min(1.0, len(sk_hit) / max(2, min(5, len(skills) or 2)))
    if sk_hit:
        reasons.append("skills: " + ", ".join(sorted(sk_hit)[:6]))
    best_jd = 0.0
    for jd in target_jds or []:
        t = tokenize(jd.get("text", "") + " " + jd.get("title", ""))
        if t:
            ov = len(t & jt) / len(t | jt)
            best_jd = max(best_jd, ov)
    if best_jd:
        reasons.append(f"JD similarity {best_jd:.0%}")
    desig = [d.lower() for d in prefs.get("designations", [])]
    s_title = 1.0 if any(d in job["title"].lower() for d in desig) else (0.4 if desig else 0.7)
    if s_title == 1.0:
        reasons.append("designation match")
    exp = float(prefs.get("experience_years") or profile_data.get("total_experience_years") or 0)
    ok_exp = job.get("min_exp", 0) <= exp <= job.get("max_exp", 99)
    if not ok_exp:
        reasons.append("experience outside band")
    pay_min = float(prefs.get("salary_min_lpa") or 0)
    ok_pay = (job.get("salary_max_lpa") or 0) >= pay_min
    if not ok_pay:
        reasons.append("pay below floor")
    modes = [m.lower() for m in prefs.get("work_modes", [])]
    ok_mode = (not modes) or (job.get("work_mode", "").lower() in modes)
    if not ok_mode:
        reasons.append("work mode mismatch")
    locs = [l.lower() for l in prefs.get("locations", [])]
    ok_loc = (not locs) or any(l in job.get("location", "").lower() for l in locs) or job.get("work_mode", "").lower() == "remote"
    if not ok_loc:
        reasons.append("location mismatch")
    hard = ok_exp and ok_pay and ok_mode and ok_loc
    score = (0.45 * s_skill + 0.35 * min(1, best_jd * 3) + 0.20 * s_title) * 100
    if not hard:
        score *= 0.3
    return round(score, 1), reasons, hard


def draft_answer(question: str, profile_data: dict, prefs: dict):
    """Drafts an answer to a screening question from the profile. Returns (answer, source, confident)."""
    q = question.lower()
    pd = profile_data
    if "notice" in q:
        return f"{pd.get('notice_period_days', 30)} days", "profile", True
    if "current ctc" in q or "current salary" in q or "current compensation" in q:
        return f"{pd.get('current_ctc_lpa', 0)} LPA", "profile", bool(pd.get("current_ctc_lpa"))
    if "expected" in q and ("ctc" in q or "salary" in q or "compensation" in q):
        v = prefs.get("salary_min_lpa")
        return (f"{v} LPA", "profile", True) if v else ("", "none", False)
    if "experience" in q and "year" in q:
        return str(prefs.get("experience_years") or pd.get("total_experience_years") or ""), "profile", True
    if "relocat" in q:
        return ("Yes" if prefs.get("relocate") else "No"), "profile", "relocate" in prefs
    if "work from office" in q or "hybrid" in q or "remote" in q:
        wm = prefs.get("work_modes") or []
        return (", ".join(wm) if wm else ""), "profile", bool(wm)
    data, used = ask_json("Answer the job-application screening question for the candidate in <= 25 words using only the given profile. "
                          "Return JSON {\"answer\": str, \"confident\": bool}. If the answer needs the candidate's own decision "
                          "(legal, visa, salary negotiation, consent), set confident=false.",
                          f"Question: {question}\nProfile: {json.dumps(pd)[:3000]}\nPreferences: {json.dumps(prefs)}", 200)
    if used and data and "answer" in data:
        return data.get("answer", ""), "claude-draft", bool(data.get("confident"))
    return "", "none", False
