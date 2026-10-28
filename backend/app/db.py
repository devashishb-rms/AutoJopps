import json
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from .config import settings, ROOT

url = settings.DATABASE_URL
if url.startswith("sqlite:///./"):
    url = "sqlite:///" + str(ROOT / url[len("sqlite:///./"):])
engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def now():
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    name = Column(String, default="")
    picture = Column(String, default="")
    google_sub = Column(String, default="")
    gmail_connected = Column(Boolean, default=False)
    gmail_refresh_token = Column(String, default="")
    created_at = Column(DateTime, default=now)
    onboarding_step = Column(Integer, default=0)  # 0 resume, 1 form, 2 prefs, 3 jds, 4 notify, 5 plan, 6 gmail, 7 done
    agent_enabled = Column(Boolean, default=False)
    approval_mode = Column(String, default="auto")  # auto | approve_each


class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    filename = Column(String)
    path = Column(String)
    text = Column(Text, default="")
    parsed = Column(JSON, default=dict)
    parser = Column(String, default="")
    created_at = Column(DateTime, default=now)


class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    data = Column(JSON, default=dict)          # Naukri-like onboarding form
    preferences = Column(JSON, default=dict)   # job types, designations, exp, pay, locations, work mode, skills
    target_jds = Column(JSON, default=list)    # [{title, company, text}]
    notify = Column(JSON, default=dict)        # {email, whatsapp, email_consent, whatsapp_consent, consent_at}
    updated_at = Column(DateTime, default=now, onupdate=now)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    plan = Column(String)
    status = Column(String, default="active")  # active | cancelled | expired
    provider = Column(String, default="demo")  # demo | razorpay
    provider_ref = Column(String, default="")
    started_at = Column(DateTime, default=now)
    ends_at = Column(DateTime)


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    plan = Column(String)
    amount_paise = Column(Integer)
    provider = Column(String)
    order_id = Column(String, default="")
    payment_id = Column(String, default="")
    status = Column(String, default="created")
    created_at = Column(DateTime, default=now)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    portal = Column(String, index=True)
    external_id = Column(String, index=True)
    title = Column(String)
    company = Column(String)
    location = Column(String, default="")
    work_mode = Column(String, default="")
    min_exp = Column(Integer, default=0)
    max_exp = Column(Integer, default=99)
    salary_min_lpa = Column(Float, default=0)
    salary_max_lpa = Column(Float, default=0)
    skills = Column(JSON, default=list)
    description = Column(Text, default="")
    url = Column(String, default="")
    posted_at = Column(DateTime, default=now)


class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), index=True)
    state = Column(String, default="matched", index=True)
    # discovered, matched, queued, preparing, awaiting_approval, submitting, needs_human, submitted, viewed, in_process, shortlisted, rejected, skipped, failed
    score = Column(Float, default=0)
    match_reasons = Column(JSON, default=list)
    tailored = Column(JSON, default=dict)      # {headline, summary, answers}
    hitl = Column(JSON, default=dict)          # {kind, question, field, options, hint, created_at}
    hitl_response = Column(JSON, default=dict)
    history = Column(JSON, default=list)       # [{at, from, to, note}]
    external_ref = Column(String, default="")
    proof_path = Column(String, default="")
    cost_inr = Column(Float, default=0)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)
    submitted_at = Column(DateTime)
    job = relationship("Job")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    channel = Column(String)   # in_app | email | whatsapp | sms_demo
    kind = Column(String)      # hitl | submitted | status | info | otp
    title = Column(String)
    body = Column(Text, default="")
    application_id = Column(Integer, nullable=True)
    delivered = Column(String, default="in_app")  # in_app | sent | logged | failed:<reason>
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class AnswerMemory(Base):
    __tablename__ = "answer_memory"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    question = Column(Text)
    normalized = Column(Text, index=True)
    answer = Column(Text)
    source = Column(String, default="user")  # user | profile | claude-draft(confirmed)
    confirmed = Column(Boolean, default=True)
    uses = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class Skill(Base):
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True)
    portal = Column(String, index=True)
    version = Column(Integer, default=1)
    status = Column(String, default="active")  # draft | trial | active | retired
    steps = Column(JSON, default=list)
    runs = Column(Integer, default=0)
    successes = Column(Integer, default=0)
    repairs = Column(Integer, default=0)
    origin = Column(String, default="built-in")  # built-in | recorded | repaired
    created_at = Column(DateTime, default=now)


class Recording(Base):
    __tablename__ = "recordings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    application_id = Column(Integer, nullable=True)
    portal = Column(String)
    events = Column(JSON, default=list)
    consent = Column(Boolean, default=False)
    distilled_skill_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=now)


class RunLog(Base):
    __tablename__ = "run_logs"
    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, index=True)
    at = Column(DateTime, default=now)
    level = Column(String, default="info")
    message = Column(Text)


def init_db():
    Base.metadata.create_all(engine)


@contextmanager
def session():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
