import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from app.database import SessionLocal
from app.models import Bot, Company, Conversation, Document, Message
from app.services import telegram
from app.services.chat import HANDOFF, is_arabic, reply_to
from app.services.crypto import decrypt
from app.services.plans import usage
from app.workers.celery_app import celery

log = logging.getLogger(__name__)

HOURLY_LIMIT = 20


@celery.task(name="handle_message")
def handle_message(bot_id: int, update_json: dict):
    msg = update_json.get("message") or {}
    text = (msg.get("text") or "").strip()

    if not text:
        return

    chat = msg.get("chat") or {}
    chat_id = chat.get("id")

    if chat_id is None:
        return

    command = text.split(maxsplit=1)[0].split("@", 1)[0]

    with SessionLocal() as db:
        bot = db.get(Bot, bot_id)

        if not bot or not bot.active:
            return

        company = db.get(Company, bot.company_id)

        if not company:
            return

        token = decrypt(bot.token_encrypted)

        # 1) المحادثة الحالية أو إنشاء محادثة جديدة
        conv = db.scalar(
            select(Conversation)
            .where(
                Conversation.bot_id == bot.id,
                Conversation.tg_chat_id == chat_id,
                Conversation.status != "closed",
            )
            .order_by(Conversation.id.desc())
        )

        if not conv:
            name = " ".join(
                filter(
                    None,
                    [
                        chat.get("first_name"),
                        chat.get("last_name"),
                    ],
                )
            ) or chat.get("title") or "عميل"

            conv = Conversation(
                company_id=company.id,
                bot_id=bot.id,
                tg_chat_id=chat_id,
                customer_name=name,
                username=chat.get("username", ""),
                lang="ar" if is_arabic(text) else "en",
            )

            db.add(conv)
            db.flush()

        # 2) أمر البداية
        if command == "/start":
            welcome = company.welcome or "أهلا بيك!"
            telegram.send_message(token, chat_id, welcome)
            db.commit()
            return

        # 3) طلب موظف: يُنفذ قبل حدود الرسائل ورصيد الخطة
        if command == "/human":
            lang = "ar" if is_arabic(text) else "en"
            reply = HANDOFF[lang]

            db.add(
                Message(
                    company_id=company.id,
                    conversation_id=conv.id,
                    role="customer",
                    content=text,
                )
            )

            conv.last_preview = reply[:200]
            conv.last_message_at = func.now()
            conv.status = "needs_human"
            conv.handoff_reason = "طلب موظف"

            db.add(
                Message(
                    company_id=company.id,
                    conversation_id=conv.id,
                    role="system",
                    content="البوت حوّل المحادثة: طلب موظف · الرد التلقائي متوقف",
                )
            )

            db.add(
                Message(
                    company_id=company.id,
                    conversation_id=conv.id,
                    role="bot",
                    content=reply,
                    flag="handoff",
                )
            )

            db.commit()
            telegram.send_message(token, chat_id, reply)
            return

        # 4) حساب حد الرسائل بالساعة
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)

        recent = (
            db.scalar(
                select(func.count())
                .select_from(Message)
                .join(
                    Conversation,
                    Message.conversation_id == Conversation.id,
                )
                .where(
                    Conversation.company_id == company.id,
                    Conversation.bot_id == bot.id,
                    Conversation.tg_chat_id == chat_id,
                    Message.company_id == company.id,
                    Message.role == "customer",
                    Message.created_at >= hour_ago,
                )
            )
            or 0
        )

        if recent >= HOURLY_LIMIT:
            return

        # 5) التحقق من رصيد الخطة
        plan_usage = usage(db, company.id, company.plan)

        if (
            plan_usage["messages_limit"] is not None
            and plan_usage["messages"] >= plan_usage["messages_limit"]
        ):
            telegram.send_message(
                token,
                chat_id,
                "الخدمة مش متاحة دلوقتي. جرّب تتواصل مع الفريق مباشرة.",
            )
            return

        # 6) حفظ تاريخ المحادثة قبل الرسالة الحالية
        history = [
            {
                "role": m.role,
                "content": m.content,
            }
            for m in reversed(
                db.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conv.id,
                        Message.role.in_(["customer", "bot", "agent"]),
                    )
                    .order_by(Message.id.desc())
                    .limit(6)
                ).all()
            )
        ]

        prev_flag = db.scalar(
            select(Message.flag)
            .where(
                Message.conversation_id == conv.id,
                Message.role == "bot",
            )
            .order_by(Message.id.desc())
            .limit(1)
        )

        # 7) حفظ رسالة العميل
        cust_msg = Message(
            company_id=company.id,
            conversation_id=conv.id,
            role="customer",
            content=text,
        )

        db.add(cust_msg)

        conv.last_preview = text[:200]
        conv.last_message_at = func.now()

        # 8) لو موظف مستلم المحادثة، البوت لا يرد
        if conv.status in ("needs_human", "human"):
            db.commit()
            return

        # 9) إرسال مؤشر الكتابة والرد
        try:
            telegram.typing(token, chat_id)

            t0 = time.time()
            result = reply_to(db, company, text, history)
            latency = int((time.time() - t0) * 1000)

        except Exception:
            log.exception("reply failed")

            db.commit()

            telegram.send_message(
                token,
                chat_id,
                "حصلت مشكلة مؤقتة. جرّب تبعت رسالتك تاني بعد شوية.",
            )
            return

        # 10) تحديد هل المحادثة تحتاج موظفًا
        in_scope = bool(result.get("in_scope", False))
        needs_human = bool(result.get("needs_human", False))

        immediate_handoff = (
            not in_scope
            and company.handoff_out_of_scope
        )

        second_failed_attempt = (
            not in_scope
            and company.handoff_after_two
            and prev_flag == "out_of_scope"
        )

        handoff = (
            needs_human
            or immediate_handoff
            or second_failed_attempt
        )

        # 11) تحديد حالة الرد
        if handoff:
            flag = "handoff"
        elif not in_scope:
            flag = "out_of_scope"
        else:
            flag = "auto"

        if not in_scope:
            cust_msg.unanswered = True

        answer = (
            result.get("answer")
            or "مش قادر أجاوب على السؤال ده حاليًا."
        )

        # 12) حفظ رد البوت
        db.add(
            Message(
                company_id=company.id,
                conversation_id=conv.id,
                role="bot",
                content=answer,
                source=result.get("source"),
                flag=flag,
                latency_ms=latency,
            )
        )

        conv.last_preview = answer[:200]

        # 13) تحديث استخدام المستند
        if result.get("source"):
            db.execute(
                update(Document)
                .where(
                    Document.company_id == company.id,
                    Document.name == result["source"],
                )
                .values(uses=Document.uses + 1)
            )

        # 14) تحويل المحادثة لموظف
        if handoff:
            conv.status = "needs_human"

            if needs_human:
                conv.handoff_reason = result.get("reason") or "طلب موظف"
            elif second_failed_attempt:
                conv.handoff_reason = (
                    "فشل البوت في الإجابة مرتين متتاليتين"
                )
            else:
                conv.handoff_reason = (
                    "السؤال خارج نطاق معلومات الشركة"
                )

            db.add(
                Message(
                    company_id=company.id,
                    conversation_id=conv.id,
                    role="system",
                    content=(
                        f"البوت حوّل المحادثة: {conv.handoff_reason}"
                        " · الرد التلقائي متوقف"
                    ),
                )
            )

        # 15) حفظ التغييرات
        db.commit()

        # 16) إرسال الرد للعميل
        telegram.send_message(token, chat_id, answer)