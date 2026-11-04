from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), index=True)
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    customer_name: Mapped[str] = mapped_column(String(200), default="عميل")
    username: Mapped[str] = mapped_column(String(100), default="")
    lang: Mapped[str] = mapped_column(String(5), default="ar")
    status: Mapped[str] = mapped_column(String(20), default="bot")  # bot | needs_human | human | closed
    handoff_reason: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    last_preview: Mapped[str] = mapped_column(String(200), default="")
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
