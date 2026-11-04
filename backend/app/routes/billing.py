
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import current_company
from app.models import Company
from app.services.plans import PLANS, usage

import logging

router = APIRouter(prefix="/billing", tags=["billing"])
log = logging.getLogger("teledesk.billing")


class PlanIn(BaseModel):
    plan: str = Field(min_length=1, max_length=50)


@router.get("")
def billing(
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    current_plan = c.plan

    if current_plan not in PLANS:
        raise HTTPException(
            500,
            "خطة الشركة الحالية غير معروفة",
        )

    return {
        "plan": current_plan,
        "plans": PLANS,
        "usage": usage(db, c.id, current_plan),
    }


@router.post("/plan")
def change_plan(
    body: PlanIn,
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    """
    وضع التطوير فقط:
    تغيير الخطة بدون دفع.

    يجب استبدال هذا المسار بنظام دفع حقيقي
    قبل الإطلاق التجاري.
    """

    new_plan = body.plan.strip().lower()

    if new_plan not in PLANS:
        raise HTTPException(
            400,
            "خطة غير معروفة",
        )

    old_plan = c.plan

    if old_plan == new_plan:
        return {
            "ok": True,
            "plan": new_plan,
        }

    try:
        c.plan = new_plan
        db.commit()
        db.refresh(c)

    except Exception:
        db.rollback()

        log.exception(
            "Failed to change company plan: company_id=%s",
            c.id,
        )

        raise HTTPException(
            500,
            "حصل خطأ أثناء تغيير الخطة",
        )

    return {
        "ok": True,
        "plan": c.plan,
    }
