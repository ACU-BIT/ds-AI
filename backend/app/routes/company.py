
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import current_company
from app.models import Company

router = APIRouter(prefix="/company", tags=["company"])
log = logging.getLogger("teledesk.company")


FIELDS = [
    "name",
    "industry",
    "description",
    "welcome",
    "tone",
    "reply_language",
    "handoff_on_request",
    "handoff_out_of_scope",
    "handoff_keywords",
    "handoff_after_two",
    "work_hours",
]


class CompanyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    industry: str = Field(default="", max_length=150)
    description: str = Field(default="", max_length=5000)
    welcome: str = Field(default="", max_length=2000)

    tone: str = Field(default="friendly", max_length=30)
    reply_language: str = Field(default="auto", max_length=20)

    handoff_on_request: bool = True
    handoff_out_of_scope: bool = True

    handoff_keywords: str = Field(default="", max_length=2000)
    handoff_after_two: bool = False
    work_hours: str = Field(default="", max_length=1000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        value = value.strip()

        if not value:
            raise ValueError("اسم الشركة مطلوب")

        return value

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, value):
        allowed = {
            "friendly",
            "professional",
            "formal",
            "casual",
        }

        if value not in allowed:
            raise ValueError("نبرة الرد غير صحيحة")

        return value

    @field_validator("reply_language")
    @classmethod
    def validate_language(cls, value):
        allowed = {
            "auto",
            "ar",
            "en",
        }

        if value not in allowed:
            raise ValueError("لغة الرد غير صحيحة")

        return value


@router.get("")
def get_company(
    c: Company = Depends(current_company),
):
    return {
        field: getattr(c, field)
        for field in FIELDS
    }


@router.put("")
def update_company(
    body: CompanyIn,
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    try:
        values = body.model_dump()

        for key, value in values.items():
            setattr(c, key, value)

        db.commit()
        db.refresh(c)

    except Exception:
        db.rollback()

        log.exception(
            "Failed to update company settings: company_id=%s",
            c.id,
        )

        raise HTTPException(
            500,
            "حصل خطأ أثناء حفظ إعدادات الشركة",
        )

    return {"ok": True}
