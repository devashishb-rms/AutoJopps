"""Drives the whole flow through the HTTP API (no UI): sign in, resume, form, prefs, JDs, notify, plan, start agent,
answer every human-help request (login via demo-login, OTP from the demo phone, questions, human check), then check tracking."""
import time, sys, httpx
B = "http://localhost:8000"
c = httpx.Client(base_url=B, timeout=30)
r = c.post("/api/auth/demo", json={"email": "devashish.demo@example.com", "name": "Devashish"}); print("login", r.status_code, r.json()["email"])
r = c.post("/api/profile/resume", files={"file": ("sample_resume.txt", open("samples/sample_resume.txt", "rb"), "text/plain")}); print("resume", r.status_code, r.json()["parser"], r.json()["parsed"]["skills"][:5])
c.put("/api/profile/form", json={"data": {"name": "Devashish Bhattacharjee", "phone": "+919810000000", "total_experience_years": 18, "current_ctc_lpa": 60, "notice_period_days": 30}})
c.put("/api/profile/preferences", json={"preferences": {"designations": ["CTO", "Head of Engineering", "Platform Architect", "Director of Engineering", "VP Engineering"],
      "experience_years": 18, "salary_min_lpa": 60, "locations": ["New Delhi", "Gurugram", "Noida", "Remote"], "work_modes": ["remote", "hybrid"], "relocate": False,
      "skills": ["python", "aws", "kubernetes", "architecture", "leadership", "fraud", "aml", "llm", "microservices", "postgres"]}})
r = c.put("/api/profile/target-jds", json={"target_jds": [{"title": "CTO", "text": "Lead engineering, architecture, platform, python aws kubernetes microservices, leadership of 10+ engineers, fintech fraud aml"},
      {"title": "Platform Architect", "text": "architecture microservices python postgres kafka kubernetes aws leadership"}]}); print("jds", r.status_code)
c.put("/api/profile/notify", json={"email": "devashish.demo@example.com", "whatsapp": "+919810000000", "email_consent": True, "whatsapp_consent": True})
r = c.post("/api/billing/demo-activate", json={"plan": "premium"}); print("plan", r.json())
r = c.post("/api/agent/discover"); print("discover", r.json())
r = c.post("/api/agent/toggle", json={"enabled": True}); print("agent", r.json())
seen = set(); t0 = time.time()
while time.time() - t0 < 240:
    st = c.get("/api/agent/status").json()
    aid, s = st["active_application"], st["active_state"]
    if s in ("needs_human", "awaiting_approval"):
        d = c.get(f"/api/applications/{aid}").json(); h = d["hitl"]; k = h.get("kind")
        key = (aid, k, h.get("question"), h.get("created_at"))
        if key in seen: time.sleep(1); continue
        seen.add(key); print("HITL", aid, k, h.get("question", ""))
        if k == "login":
            c.post(f"/api/agent/hitl/{aid}/demo-login"); time.sleep(2); c.post(f"/api/agent/hitl/{aid}/login-done")
        elif k == "otp":
            otp = None
            for _ in range(10):
                otp = c.get("/api/agent/demo-phone").json().get("otp")
                if otp: break
                time.sleep(1)
            print("  demo phone OTP:", otp); c.post(f"/api/agent/hitl/{aid}", json={"action": "value", "value": otp})
        elif k == "question":
            c.post(f"/api/agent/hitl/{aid}", json={"action": "value", "value": {"Do you hold any patents or publications?": "No patents; two internal whitepapers on fraud detection.", "Which of our products have you used?": "I have evaluated your public product as a prospective user."}.get(h.get("question"), "Yes.")})
        elif k == "captcha":
            word = None
            for _ in range(10):
                word = c.get("/portal/_demo/last-check", params={"email": "devashish.demo@example.com"}).json().get("word")
                if word: break
                time.sleep(1)
            print("  human-check word (test helper):", word); c.post(f"/api/agent/hitl/{aid}", json={"action": "value", "value": word})
        elif k == "approve":
            c.post(f"/api/agent/hitl/{aid}", json={"action": "approve"})
    apps = c.get("/api/applications").json()
    if apps["funnel"]["submitted"] >= 1 and st["active_application"] is None:
        print("submitted >= 1; funnel", apps["funnel"]); break
    time.sleep(1.5)
d = c.get("/api/applications").json()
print("counts", d["counts"])
sub = [a for a in d["applications"] if a["state"] in ("submitted", "viewed")]
if sub:
    det = c.get(f"/api/applications/{sub[0]['id']}").json()
    print("ref", det["external_ref"]); [print("  ", l["level"], l["message"]) for l in det["logs"]]
print("learning", {k: len(v) for k, v in c.get("/api/learning").json().items()})
print("notifications", [(n["channel"], n["kind"], n["delivered"]) for n in c.get("/api/notifications").json()[:6]])
print("admin", c.get("/api/admin/stats").json())
