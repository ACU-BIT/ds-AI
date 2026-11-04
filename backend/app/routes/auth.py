
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import (
    current_company,
    current_user,
    hash_password,
    make_token,
    verify_password,
)
from app.models import Bot, Company, Conversation, User
from app.services.plans import PLANS, usage

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("teledesk.auth")


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def _create(
    db: Session,
    name: str,
    email: str,
    password: str,
    plan: str = "free",
) -> User:
    name = name.strip()
    email = email.strip().lower()

    if not name:
        raise HTTPException(400, "اكتب اسمك")

    if len(name) > 150:
        raise HTTPException(400, "الاسم طويل جدًا")

    if len(password) < 8:
        raise HTTPException(
            400,
            "كلمة المرور لازم 8 حروف على الأقل",
        )

    if len(password) > 128:
        raise HTTPException(400, "كلمة المرور طويلة جدًا")

    if plan not in PLANS:
        raise HTTPException(400, "الخطة غير معروفة")

    existing = db.scalar(
        select(User).where(User.email == email)
    )

    if existing:
        raise HTTPException(
            400,
            "البريد ده مسجّل قبل كده. جرّب تسجيل الدخول",
        )

    try:
        company = Company(
            name=f"شركة {name}",
            plan=plan,
        )

        db.add(company)
        db.flush()

        user = User(
            company_id=company.id,
            name=name,
            email=email,
            password_hash=hash_password(password),
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            400,
            "البريد ده مسجّل قبل كده. جرّب تسجيل الدخول",
        )

    except Exception:
        db.rollback()

        log.exception("Account creation failed")

        raise HTTPException(
            500,
            "حصل خطأ أثناء إنشاء الحساب",
        )


@router.post("/register")
def register(
    body: RegisterIn,
    db: Session = Depends(get_db),
):
    user = _create(
        db,
        body.name,
        str(body.email),
        body.password,
    )

    return {
        "token": make_token(user.id),
    }


@router.post("/login")
def login(
    body: LoginIn,
    db: Session = Depends(get_db),
):
    email = str(body.email).strip().lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if not user or not verify_password(
        body.password,
        user.password_hash,
    ):
        raise HTTPException(
            400,
            "البريد أو كلمة المرور غلط",
        )

    return {
        "token": make_token(user.id),
    }


@router.post("/demo")
def demo(
    db: Session = Depends(get_db),
):
    """
    حساب تجريبي مؤقت.
    يجب إضافة Rate Limiting أو تعطيل المسار
    قبل الإطلاق التجاري.
    """

    demo_email = (
        f"demo-{secrets.token_hex(8)}@example.com"
    )

    demo_password = secrets.token_urlsafe(24)

    user = _create(
        db,
        "حساب تجريبي",
        demo_email,
        demo_password,
        plan="pro",
    )

    return {
        "token": make_token(user.id),
    }


@router.get("/me")
def me(
    user: User = Depends(current_user),
    company: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    bot = db.scalar(
        select(Bot)
        .where(Bot.company_id == company.id)
        .limit(1)
    )

    needs_human = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.company_id == company.id,
            Conversation.status == "needs_human",
        )
    ) or 0

    plan = PLANS.get(company.plan, PLANS["free"])

    return {
        "user": {
            "name": user.name,
            "email": user.email,
        },

        "company": {
            "name": company.name,
            "plan": company.plan,
            "plan_name": plan["name"],
        },

        "usage": usage(
            db,
            company.id,
            company.plan,
        ),

        "bot": {
            "active": bot.active,
            "connected": bot.connected,
        } if bot else None,

        "needs_human": needs_human,
    }
