
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import current_company
from app.models import Bot, Company, Conversation, Message
from app.services import telegram
from app.services.chat import reply_to
from app.services.crypto import decrypt, encrypt
from app.services.plans import PLANS

router = APIRouter(prefix="/bots", tags=["bots"])
log = logging.getLogger("teledesk.bots")


class ConnectIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class TestIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def _bot(db: Session, c: Company) -> Bot | None:
    return db.scalar(
        select(Bot).where(Bot.company_id == c.id).limit(1)
    )


def _check_bot_limit(db: Session, c: Company):
    plan = PLANS.get(c.plan, PLANS["free"])
    limit = plan["bots"]

    if limit is None:
        return

    count = db.scalar(
        select(func.count())
        .select_from(Bot)
        .where(Bot.company_id == c.id)
    ) or 0

    if count >= limit:
        raise HTTPException(
            403,
            "وصلت للحد الأقصى من البوتات في باقتك. قم بترقية الباقة لإضافة بوت آخر.",
        )


@router.get("")
def get_bot(
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    bot = _bot(db, c)

    if not bot:
        return {"bot": None}

    today = func.date_trunc("day", func.now())

    today_count = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.company_id == c.id,
            Message.role == "customer",
            Message.created_at >= today,
        )
    ) or 0

    customers = db.scalar(
        select(func.count(func.distinct(Conversation.tg_chat_id)))
        .where(
            Conversation.company_id == c.id,
            Conversation.bot_id == bot.id,
        )
    ) or 0

    last = db.scalar(
        select(func.max(Message.created_at))
        .where(
            Message.company_id == c.id,
            Message.role == "customer",
        )
    )

    logs = db.execute(
        select(
            Message.flag,
            Message.content,
            Message.created_at,
            Conversation.customer_name,
        )
        .join(
            Conversation,
            Conversation.id == Message.conversation_id,
        )
        .where(
            Message.company_id == c.id,
            Message.role == "bot",
            Conversation.company_id == c.id,
            Conversation.bot_id == bot.id,
        )
        .order_by(Message.id.desc())
        .limit(10)
    ).all()

    return {
        "bot": {
            "id": bot.id,
            "name": bot.name,
            "username": bot.username,
            "active": bot.active,
            "connected": bot.connected,
            "link": f"https://t.me/{bot.username}" if bot.username else None,
        },
        "today": today_count,
        "customers": customers,
        "last_message": last.isoformat() if last else None,
        "log": [
            {
                "flag": flag,
                "customer": customer_name,
                "text": (content or "")[:70],
                "at": created_at.isoformat() if created_at else None,
            }
            for flag, content, created_at, customer_name in logs
        ],
    }


@router.post("/connect")
def connect(
    body: ConnectIn,
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    token = body.token.strip()

    if not token:
        raise HTTPException(400, "اكتب توكن البوت")

    try:
        me = telegram.get_me(token)
    except Exception:
        log.warning(
            "Telegram get_me failed for company_id=%s",
            c.id,
            exc_info=True,
        )
        raise HTTPException(
            400,
            "المفتاح غير صحيح أو غير شغال. انسخه تاني من @BotFather",
        )

    username = me.get("username")

    if not username:
        raise HTTPException(
            400,
            "تليجرام لم يرجع اسم مستخدم صالح للبوت",
        )

    taken = db.scalar(
        select(Bot).where(
            Bot.username == username,
            Bot.company_id != c.id,
        )
    )

    if taken:
        raise HTTPException(
            400,
            "البوت ده مربوط بحساب تاني",
        )

    bot = _bot(db, c)

    # نطبق حد الباقة عند إنشاء بوت جديد فقط.
    if not bot:
        _check_bot_limit(db, c)
        bot = Bot(company_id=c.id)

    try:
        bot.token_encrypted = encrypt(token)
        bot.username = username
        bot.name = me.get("first_name") or username
        bot.secret = secrets.token_urlsafe(24)
        bot.active = True
        bot.connected = False

        db.add(bot)
        db.commit()
        db.refresh(bot)

    except Exception:
        db.rollback()
        log.exception(
            "Failed to save bot connection for company_id=%s",
            c.id,
        )
        raise HTTPException(
            500,
            "حصل خطأ أثناء حفظ بيانات البوت",
        )

    base = settings.PUBLIC_BASE_URL.rstrip("/")
    warning = None

    if base.startswith("https://"):
        try:
            telegram.set_webhook(
                token,
                f"{base}/webhooks/telegram/{bot.id}",
                bot.secret,
            )

            bot.connected = True
            db.commit()

        except Exception:
            db.rollback()

            log.exception(
                "Telegram webhook setup failed for bot_id=%s",
                bot.id,
            )

            warning = (
                "تم حفظ البوت، لكن تليجرام لم يتمكن من تفعيل استقبال الرسائل. "
                "راجع إعدادات Webhook."
            )

            try:
                bot = db.get(Bot, bot.id)
                if bot:
                    bot.connected = False
                    db.commit()
            except Exception:
                db.rollback()
                log.exception(
                    "Failed to update bot connection status: bot_id=%s",
                    bot.id,
                )

    else:
        warning = (
            "PUBLIC_BASE_URL غير مضبوط في ملف .env. "
            "لازم يكون عنوان HTTPS. تم حفظ البوت لكنه لن يستقبل رسائل حاليًا."
        )

    return {
        "ok": True,
        "warning": warning,
    }


@router.post("/toggle")
def toggle(
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    bot = _bot(db, c)

    if not bot:
        raise HTTPException(404, "مفيش بوت مربوط")

    if not bot.connected and not bot.active:
        raise HTTPException(
            400,
            "البوت غير متصل. أعد ربطه أولًا.",
        )

    bot.active = not bot.active

    try:
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Failed to toggle bot: bot_id=%s", bot.id)
        raise HTTPException(500, "حصل خطأ أثناء تغيير حالة البوت")

    return {"active": bot.active}


@router.post("/disconnect")
def disconnect(
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    bot = _bot(db, c)

    if not bot:
        return {"ok": True}

    try:
        token = decrypt(bot.token_encrypted)
        telegram.delete_webhook(token)

    except Exception:
        log.exception(
            "Failed to delete Telegram webhook: bot_id=%s",
            bot.id,
        )
        raise HTTPException(
            502,
            "تعذر فصل البوت من تليجرام. حاول مرة أخرى.",
        )

    try:
        db.delete(bot)
        db.commit()

    except Exception:
        db.rollback()
        log.exception(
            "Failed to delete bot from database: bot_id=%s",
            bot.id,
        )
        raise HTTPException(
            500,
            "حصل خطأ أثناء حذف البوت من قاعدة البيانات",
        )

    return {"ok": True}


@router.post("/test")
def test(
    body: TestIn,
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    question = body.question.strip()

    if not question:
        raise HTTPException(400, "اكتب سؤال")

    try:
        result = reply_to(db, c, question, [])

    except Exception:
        log.exception(
            "Bot test failed for company_id=%s",
            c.id,
        )
        raise HTTPException(
            502,
            "حصلت مشكلة أثناء اختبار الاتصال بخدمة الذكاء الاصطناعي",
        )

    return {
        "answer": result["answer"],
        "source": result.get("source"),
        "needs_human": result["needs_human"],
        "in_scope": result["in_scope"],
    }