
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Bot, Document, Message


# None = بدون حد
PLANS = {
    "free": {
        "name": "مجانية",
        "price": 0,
        "messages": 100,
        "files": 5,
        "bots": 1,
    },
    "starter": {
        "name": "Starter",
        "price": 29,
        "messages": 2000,
        "files": 50,
        "bots": 1,
    },
    "pro": {
        "name": "Pro",
        "price": 79,
        "messages": 10000,
        "files": 500,
        "bots": 3,
    },
    "business": {
        "name": "Business",
        "price": 199,
        "messages": None,
        "files": None,
        "bots": None,
    },
}


def month_start() -> datetime:
    """بداية الشهر الحالي بتوقيت UTC."""
    now = datetime.now(timezone.utc)

    return now.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def usage(
    db: Session,
    company_id: int,
    plan: str,
) -> dict:
    """
    حساب استهلاك الشركة:
    - رسائل العملاء خلال الشهر الحالي.
    - عدد المستندات المسجلة.
    - عدد البوتات المسجلة.
    - إجمالي مساحة المستندات بالبايت.
    """

    if not isinstance(company_id, int) or company_id <= 0:
        raise ValueError("Invalid company_id")

    # الخطة غير المعروفة تستخدم حدود المجانية كإجراء احترازي.
    p = PLANS.get(plan, PLANS["free"])

    start = month_start()

    messages_count = (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.company_id == company_id,
                Message.role == "customer",
                Message.created_at >= start,
            )
        )
        or 0
    )

    files_count = (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.company_id == company_id,
            )
        )
        or 0
    )

    bots_count = (
        db.scalar(
            select(func.count())
            .select_from(Bot)
            .where(
                Bot.company_id == company_id,
            )
        )
        or 0
    )

    storage_size = (
        db.scalar(
            select(func.coalesce(func.sum(Document.size), 0))
            .where(
                Document.company_id == company_id,
            )
        )
        or 0
    )

    return {
        "messages": int(messages_count),
        "messages_limit": p["messages"],

        "files": int(files_count),
        "files_limit": p["files"],

        "bots": int(bots_count),
        "bots_limit": p["bots"],

        "storage_bytes": int(storage_size),
    }
