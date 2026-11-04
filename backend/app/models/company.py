from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    welcome: Mapped[str] = mapped_column(Text, default="أهلا بيك! تحب أساعدك في إيه؟")
    tone: Mapped[str] = mapped_column(String(20), default="friendly")  # friendly | professional | formal
    reply_language: Mapped[str] = mapped_column(String(10), default="auto")  # auto | ar | en
    handoff_on_request: Mapped[bool] = mapped_column(Boolean, default=True)
    handoff_out_of_scope: Mapped[bool] = mapped_column(Boolean, default=True)
    handoff_keywords: Mapped[str] = mapped_column(Text, default="شكوى,استرداد,مكسور")
    handoff_after_two: Mapped[bool] = mapped_column(Boolean, default=False)
    work_hours: Mapped[str] = mapped_column(String(200), default="")
    plan: Mapped[str] = mapped_column(String(20), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
