import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_env():
    for p in (ROOT / ".env", ROOT / "backend" / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


def env(k, default=""):
    return os.environ.get(k, default)


class Settings:
    SECRET = env("APP_SECRET", "dev-secret-change-me")
    BASE_URL = env("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    ENV = env("APP_ENV", "dev")
    DATABASE_URL = env("DATABASE_URL", "sqlite:///./autojopps.db")
    GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET")
    GOOGLE_GMAIL_SCOPE = env("GOOGLE_GMAIL_SCOPE", "0") == "1"
    ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-haiku-4-5")
    RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET")
    SMTP_HOST = env("SMTP_HOST")
    SMTP_PORT = int(env("SMTP_PORT", "587") or 587)
    SMTP_USER = env("SMTP_USER")
    SMTP_PASSWORD = env("SMTP_PASSWORD")
    SMTP_FROM = env("SMTP_FROM", "AutoJopps <no-reply@example.com>")
    WHATSAPP_TOKEN = env("WHATSAPP_TOKEN")
    WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID")
    WHATSAPP_TEMPLATE_NAME = env("WHATSAPP_TEMPLATE_NAME", "autojopps_hitl")
    RUNNER_HEADLESS = env("RUNNER_HEADLESS", "1") == "1"
    RUNNER_SLOWMO_MS = int(env("RUNNER_SLOWMO_MS", "150") or 0)
    TICK = float(env("ORCHESTRATOR_TICK_SECONDS", "5") or 5)
    UPLOAD_DIR = ROOT / "data" / "uploads"
    SHOT_DIR = ROOT / "data" / "shots"

    @property
    def google_enabled(self):
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)

    @property
    def claude_enabled(self):
        return bool(self.ANTHROPIC_API_KEY)

    @property
    def razorpay_enabled(self):
        return bool(self.RAZORPAY_KEY_ID and self.RAZORPAY_KEY_SECRET)

    @property
    def smtp_enabled(self):
        return bool(self.SMTP_HOST)

    @property
    def whatsapp_enabled(self):
        return bool(self.WHATSAPP_TOKEN and self.WHATSAPP_PHONE_NUMBER_ID)

    def modes(self):
        return {
            "google": "live" if self.google_enabled else "demo",
            "gmail_scope": self.GOOGLE_GMAIL_SCOPE,
            "claude": "live" if self.claude_enabled else "heuristic",
            "razorpay": "test" if self.razorpay_enabled else "demo",
            "email": "smtp" if self.smtp_enabled else "in-app only",
            "whatsapp": "cloud-api" if self.whatsapp_enabled else "in-app only",
            "runner": "headless" if self.RUNNER_HEADLESS else "headed",
        }


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.SHOT_DIR.mkdir(parents=True, exist_ok=True)

PLANS = {
    "basic": {"name": "Basic", "price_inr": 501, "daily_cap": 5, "monthly_cap": 100, "runners": 1, "planner": False},
    "premium": {"name": "Premium", "price_inr": 1001, "daily_cap": 10, "monthly_cap": 200, "runners": 2, "planner": True},
    "ultra": {"name": "Ultra", "price_inr": 2001, "daily_cap": 20, "monthly_cap": 400, "runners": 4, "planner": True},
}
