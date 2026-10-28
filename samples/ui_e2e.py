"""End-to-end through the real UI with Playwright. Saves screenshots to samples/shots/."""
import time, re
from playwright.sync_api import sync_playwright
B = "http://localhost:8000"; S = "samples/shots/"
with sync_playwright() as pw:
    br = pw.chromium.launch(); pg = br.new_page(viewport={"width": 1360, "height": 900})
    pg.on("console", lambda m: print("console:", m.type, m.text) if m.type in ("error", "warning") else None); pg.on("pageerror", lambda e: print("pageerror:", e))
    pg.goto(B); pg.fill("input[placeholder='you@example.com']", "investor.demo@example.com"); pg.fill("input[placeholder='Your name']", "Demo User")
    pg.screenshot(path=S + "01_login.png"); pg.click("text=Enter demo"); pg.wait_for_url("**/app/onboarding")
    pg.set_input_files("input[type=file]", "samples/sample_resume.txt"); pg.wait_for_selector("text=Your profile", timeout=20000); time.sleep(0.5)
    pg.screenshot(path=S + "02_profile_prefilled.png")
    pg.fill("xpath=//label[contains(.,'Mobile')]/following-sibling::input", "+919810000000")
    pg.click("text=Save and continue"); pg.wait_for_selector("text=What should we apply to?")
    pg.fill("input[placeholder='CTO, Head of Engineering']", "CTO, Head of Engineering, Platform Architect, Director of Engineering, VP Engineering")
    pg.fill("input[placeholder='min']", "40"); pg.fill("input[placeholder='max']", "90")
    pg.fill("xpath=//label[contains(.,'Locations')]/following-sibling::input", "New Delhi, Gurugram, Noida, Bengaluru, Remote")
    pg.screenshot(path=S + "03_targets.png"); pg.click("text=Save and continue"); pg.wait_for_selector("text=target job descriptions")
    pg.fill("xpath=(//label[text()='Title']/following-sibling::input)[1]", "CTO")
    pg.fill("textarea", "Lead engineering and architecture for a fintech platform: python, aws, kubernetes, microservices, postgres, kafka; leadership of 10+ engineers; fraud and AML domain.")
    pg.click("text=Add another"); pg.fill("xpath=(//label[text()='Title']/following-sibling::input)[2]", "Platform Architect")
    pg.fill("xpath=(//textarea)[2]", "Platform architect: architecture, microservices, python, postgres, kafka, kubernetes, aws, leadership, data platform.")
    pg.click("text=Save and continue"); pg.wait_for_selector("text=Where should we reach you")
    pg.fill("input[placeholder='+91 98xxxxxxxx']", "+919810000000"); pg.check("xpath=//label[contains(.,'WhatsApp messages')]/input")
    pg.screenshot(path=S + "04_consent.png"); pg.click("text=Save and continue"); pg.wait_for_selector("text=Choose a plan")
    pg.screenshot(path=S + "05_plans.png"); pg.click("xpath=(//button[contains(.,'Activate (demo)')])[2]"); pg.wait_for_selector("text=Connect the Gmail account", timeout=15000)
    pg.click("text=Connect with forwarding alias"); time.sleep(0.5); pg.screenshot(path=S + "06_gmail.png"); pg.click("text=Continue"); pg.wait_for_selector("text=You are set")
    pg.click("text=Start applying"); pg.wait_for_url("**/app"); time.sleep(1); pg.screenshot(path=S + "07_overview.png")
    # ---- help the bot: login via live view (click + type on the streamed screen)
    pg.wait_for_selector("text=One-time sign-in needed", timeout=60000); time.sleep(2.5)
    pg.screenshot(path=S + "08_hitl_login_liveview.png")
    img = pg.locator(".live img").first; box = img.bounding_box()
    sx, sy = box["width"] / 1100, box["height"] / 760
    # email field centre in the mock portal ~ (430, 282); password ~ (430, 352); button ~ (300, 412) -> locate from a screenshot of the live browser instead:
    pg.click("text=Demo: type portal credentials for me"); time.sleep(2.5)
    pg.screenshot(path=S + "09_after_demo_login.png")
    pg.click("text=I have signed in, continue")
    pg.wait_for_selector("text=OTP needed", timeout=30000)
    pg.wait_for_selector("text=SMS received", timeout=15000); time.sleep(0.5); pg.screenshot(path=S + "10_hitl_otp.png")
    otp = re.search(r"\d{4}", pg.locator(".ok.small").inner_text()).group(0)
    pg.fill("input[placeholder='4-digit OTP']", otp); pg.click("text=Submit OTP")
    # questions / captcha loop
    t0 = time.time(); done = False
    while time.time() - t0 < 180 and not done:
        time.sleep(1.5)
        if pg.locator(".kpi .n").first.inner_text() != "0":
            done = True
        elif pg.locator(".alert h3:has-text('A question only you can answer')").count():
            q = pg.locator(".alert p.small").first.inner_text(); print("Q:", q)
            pg.fill("textarea", "Yes. " + ("I led 40+ engineers across three teams." if "team" in q else "I have reviewed your product as a prospective user." if "product" in q else "Not applicable."))
            pg.screenshot(path=S + "11_hitl_question.png"); pg.click("text=Answer and remember"); time.sleep(2)
        elif pg.locator(".alert h3:has-text('Human check')").count():
            time.sleep(2); pg.screenshot(path=S + "12_hitl_captcha_liveview.png")
            import httpx; w = httpx.get(B + "/portal/_demo/last-check", params={"email": "investor.demo@example.com"}).json()["word"]
            if w:
                pg.fill("input[placeholder='Type the word you see']", w); pg.click(".alert button:has-text('Submit')"); time.sleep(3)
    time.sleep(1); pg.screenshot(path=S + "13_overview_after_submit.png")
    pg.click("text=Pause agent"); time.sleep(0.5)
    pg.goto(B + "/app/applications"); pg.wait_for_selector("table"); pg.click("text=applied"); time.sleep(0.5); pg.click("xpath=(//tbody//a)[1]"); time.sleep(1.5)
    pg.screenshot(path=S + "14_application_detail.png", full_page=True)
    pg.goto(B + "/app/learning"); time.sleep(1); pg.screenshot(path=S + "15_learning.png", full_page=True)
    pg.goto(B + "/app/admin"); time.sleep(1); pg.screenshot(path=S + "16_admin.png")
    pg.goto(B + "/app/settings"); time.sleep(1); pg.screenshot(path=S + "17_settings.png")
    print("E2E done:", done)
    br.close()
