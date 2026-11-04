
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import current_company
from app.models import Bot, Company, Conversation, Message
from app.services import telegram
from app.services.crypto import decrypt

import logging

router = APIRouter(prefix="/conversations", tags=["conversations"])
log = logging.getLogger("teledesk.conversations")


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class NoteIn(BaseModel):
    note: str = Field(max_length=2000)


def _get(db: Session, c: Company, cid: int) -> Conversation:
    conv = db.scalar(
        select(Conversation).where(
            Conversation.id == cid,
            Conversation.company_id == c.id,
        )
    )
    if not conv:
        raise HTTPException(404, "المحادثة مش موجودة")
    return conv


@router.get("")
def list_convs(
    status: str = "all",
    q: str = "",
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    base = select(Conversation).where(
        Conversation.company_id == c.id
    )

    counts = {
        "all": db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.company_id == c.id,
                Conversation.status != "closed",
            )
        ) or 0,
        "needs_human": db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.company_id == c.id,
                Conversation.status.in_(["needs_human", "human"]),
            )
        ) or 0,
    }

    if status == "needs_human":
        base = base.where(
            Conversation.status.in_(["needs_human", "human"])
        )
    elif status == "closed":
        base = base.where(Conversation.status == "closed")
    else:
        base = base.where(Conversation.status != "closed")

    if q.strip():
        like = f"%{q.strip()}%"
        base = base.where(
            or_(
                Conversation.customer_name.ilike(like),
                Conversation.last_preview.ilike(like),
            )
        )

    rows = db.scalars(
        base.order_by(
            Conversation.last_message_at.desc().nullslast(),
            Conversation.id.desc(),
        ).limit(100)
    ).all()

    return {
        "counts": counts,
        "items": [
            {
                "id": r.id,
                "name": r.customer_name,
                "preview": r.last_preview,
                "status": r.status,
                "at": r.last_message_at.isoformat()
                if r.last_message_at else None,
            }
            for r in rows
        ],
    }


@router.get("/{cid}")
def detail(
    cid: int,
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    conv = _get(db, c, cid)

    msgs = db.scalars(
        select(Message)
        .where(
            Message.conversation_id == cid,
            Message.company_id == c.id,
        )
        .order_by(Message.id)
    ).all()

    prev = db.scalars(
        select(Conversation)
        .where(
            Conversation.company_id == c.id,
            Conversation.tg_chat_id == conv.tg_chat_id,
            Conversation.id != cid,
        )
        .order_by(Conversation.id.desc())
        .limit(5)
    ).all()

    sources = sorted({
        m.source for m in msgs if m.source
    })

    total = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.company_id == c.id,
            Conversation.tg_chat_id == conv.tg_chat_id,
        )
    ) or 1

    return {
        "id": conv.id,
        "name": conv.customer_name,
        "username": conv.username,
        "status": conv.status,
        "lang": conv.lang,
        "reason": conv.handoff_reason,
        "note": conv.note,
        "since": conv.created_at.isoformat() if conv.created_at else None,
        "total_convs": total,
        "sources": sources,
        "previous": [
            {
                "preview": p.last_preview,
                "at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in prev
        ],
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "source": m.source,
                "at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ],
    }


@router.post("/{cid}/take")
def take(
    cid: int,
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    conv = _get(db, c, cid)

    if conv.status == "closed":
        raise HTTPException(400, "المحادثة مغلقة")

    conv.status = "human"
    db.commit()

    return {"ok": True}


@router.post("/{cid}/close")
def close(
    cid: int,
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    conv = _get(db, c, cid)
    conv.status = "closed"
    db.commit()

    return {"ok": True}


@router.post("/{cid}/note")
def note(
    cid: int,
    body: NoteIn,
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    conv = _get(db, c, cid)
    conv.note = body.note.strip()
    db.commit()

    return {"ok": True}


@router.post("/{cid}/reply")
def reply(
    cid: int,
    body: ReplyIn,
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    conv = _get(db, c, cid)

    if conv.status == "closed":
        raise HTTPException(400, "المحادثة مغلقة، افتحها قبل إرسال رد")

    message_text = body.text.strip()
    if not message_text:
        raise HTTPException(400, "اكتب الرد")

    bot = db.scalar(
        select(Bot).where(
            Bot.id == conv.bot_id,
            Bot.company_id == c.id,
        )
    )

    if not bot or not bot.token_encrypted:
        raise HTTPException(400, "البوت المرتبط بالمحادثة غير متاح")

    try:
        token = decrypt(bot.token_encrypted)
        telegram.send_message(token, conv.tg_chat_id, message_text)
    except Exception:
        log.exception(
            "Failed to send agent reply: conversation_id=%s",
            conv.id,
        )
        raise HTTPException(
            502,
            "تليجرام لم يتمكن من إرسال الرسالة",
        )

    try:
        db.add(
            Message(
                company_id=c.id,
                conversation_id=cid,
                role="agent",
                content=message_text,
            )
        )
        conv.status = "human"
        conv.last_preview = message_text[:200]
        conv.last_message_at = func.now()
        db.commit()
    except Exception:
        db.rollback()
        log.exception(
            "Failed to save agent reply: conversation_id=%s",
            conv.id,
        )
        raise HTTPException(
            500,
            "الرسالة اتبعتت، لكن حصل خطأ أثناء حفظها في السجل",
        )

    return {"ok": True}
