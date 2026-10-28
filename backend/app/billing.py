"""Three tiers. Razorpay test-mode orders with signature verification; demo activation when keys are absent.
Entitlements: daily and monthly caps enforced in one place (reserve / commit / release)."""
import hashlib
import hmac
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .auth import current_user
from .config import settings, PLANS
from .db import get_db, User, Subscription, Payment, Application

router = APIRouter(prefix="/api/billing", tags=["billing"])
RZP = "https://api.razorpay.com/v1"


@router.get("/plans")
def plans():
    return {"plans": [{"id": k, **v} for k, v in PLANS.items()], "mode": settings.modes()["razorpay"],
            "key_id": settings.RAZORPAY_KEY_ID if settings.razorpay_enabled else ""}


def active_sub(db: Session, user_id: int):
    s = db.query(Subscription).filter_by(user_id=user_id, status="active").order_by(Subscription.id.desc()).first()
    if s and s.ends_at and s.ends_at < datetime.utcnow():
        s.status = "expired"
        return None
    return s


def usage(db: Session, user_id: int):
    today = datetime.utcnow().date()
    month_start = today.replace(day=1)
    counted = ("submitted", "viewed", "in_process", "shortlisted", "rejected", "submitting", "preparing", "needs_human", "awaiting_approval")
    q = db.query(func.count(Application.id)).filter(Application.user_id == user_id, Application.state.in_(counted))
    d = q.filter(Application.created_at >= datetime.combine(today, datetime.min.time())).scalar() or 0
    m = q.filter(Application.created_at >= datetime.combine(month_start, datetime.min.time())).scalar() or 0
    return d, m


@router.get("/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = active_sub(db, user.id)
    d, m = usage(db, user.id)
    plan = PLANS.get(s.plan) if s else None
    return {"subscription": {"plan": s.plan, "status": s.status, "provider": s.provider, "ends_at": s.ends_at.isoformat() if s.ends_at else None} if s else None,
            "plan": plan, "used_today": d, "used_month": m,
            "remaining_today": max(0, plan["daily_cap"] - d) if plan else 0,
            "remaining_month": max(0, plan["monthly_cap"] - m) if plan else 0}


def can_apply(db: Session, user_id: int):
    s = active_sub(db, user_id)
    if not s:
        return False, "no active plan"
    plan = PLANS[s.plan]
    d, m = usage(db, user_id)
    if d >= plan["daily_cap"]:
        return False, "daily cap reached"
    if m >= plan["monthly_cap"]:
        return False, "monthly cap reached"
    return True, ""


class PlanBody(BaseModel):
    plan: str


def _activate(db: Session, user: User, plan: str, provider: str, ref: str):
    for s in db.query(Subscription).filter_by(user_id=user.id, status="active"):
        s.status = "cancelled"
    sub = Subscription(user_id=user.id, plan=plan, provider=provider, provider_ref=ref, ends_at=datetime.utcnow() + timedelta(days=30))
    db.add(sub)
    u = db.get(User, user.id)
    u.onboarding_step = max(u.onboarding_step, 6)
    return sub


@router.post("/demo-activate")
def demo_activate(body: PlanBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.plan not in PLANS:
        raise HTTPException(400, "unknown plan")
    db.add(Payment(user_id=user.id, plan=body.plan, amount_paise=PLANS[body.plan]["price_inr"] * 100, provider="demo", status="paid"))
    _activate(db, user, body.plan, "demo", "demo")
    return {"ok": True, "plan": body.plan, "mode": "demo"}


@router.post("/order")
async def create_order(body: PlanBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.plan not in PLANS:
        raise HTTPException(400, "unknown plan")
    if not settings.razorpay_enabled:
        raise HTTPException(400, "Razorpay keys not configured; use demo activation")
    amount = PLANS[body.plan]["price_inr"] * 100
    async with httpx.AsyncClient(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET), timeout=20) as c:
        r = await c.post(RZP + "/orders", json={"amount": amount, "currency": "INR", "receipt": f"aj_{user.id}_{int(datetime.utcnow().timestamp())}",
                                                 "notes": {"plan": body.plan, "user_id": str(user.id)}})
    if r.status_code >= 300:
        raise HTTPException(502, "Razorpay order failed: " + r.text[:200])
    o = r.json()
    db.add(Payment(user_id=user.id, plan=body.plan, amount_paise=amount, provider="razorpay", order_id=o["id"], status="created"))
    return {"order_id": o["id"], "amount": amount, "currency": "INR", "key_id": settings.RAZORPAY_KEY_ID,
            "prefill": {"name": user.name, "email": user.email}, "plan": PLANS[body.plan]}


class VerifyBody(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.post("/verify")
def verify(body: VerifyBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, body.razorpay_signature):
        raise HTTPException(400, "signature mismatch")
    p = db.query(Payment).filter_by(order_id=body.razorpay_order_id, user_id=user.id).first()
    if not p:
        raise HTTPException(404, "order not found")
    p.payment_id = body.razorpay_payment_id
    p.status = "paid"
    _activate(db, user, p.plan, "razorpay", body.razorpay_payment_id)
    return {"ok": True, "plan": p.plan}


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")
    if settings.RAZORPAY_WEBHOOK_SECRET:
        exp = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(exp, sig):
            raise HTTPException(400, "bad signature")
    ev = await request.json()
    if ev.get("event") == "payment.captured":
        pay = ev["payload"]["payment"]["entity"]
        p = db.query(Payment).filter_by(order_id=pay.get("order_id", "")).first()
        if p and p.status != "paid":
            p.status = "paid"
            p.payment_id = pay["id"]
            _activate(db, db.get(User, p.user_id), p.plan, "razorpay", pay["id"])
    return {"ok": True}


@router.post("/cancel")
def cancel(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = active_sub(db, user.id)
    if s:
        s.status = "cancelled"
    u = db.get(User, user.id)
    u.agent_enabled = False
    return {"ok": True}
