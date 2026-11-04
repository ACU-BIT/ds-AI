
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import current_company
from app.models import Company, Conversation, Message

router = APIRouter(prefix="/stats", tags=["stats"])

CAIRO = ZoneInfo("Africa/Cairo")


def _norm(value: str | None) -> str:
    if not isinstance(value, str):
        return ""

    return value.strip().strip("؟?!.،,؛;: ").lower()


def _cairo_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(CAIRO)


@router.get("/overview")
def overview(
    days: int = Query(default=7, ge=1, le=90),
    c: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    prev_since = since - timedelta(days=days)

    # رسائل العملاء في الفترتين الحالية والسابقة
    customer_messages = db.execute(
        select(
            Message.content,
            Message.created_at,
            Message.unanswered,
        ).where(
            Message.company_id == c.id,
            Message.role == "customer",
            Message.created_at >= prev_since,
            Message.created_at < now,
        )
    ).all()

    current_messages = [
        m for m in customer_messages
        if m.created_at >= since
    ]

    previous_messages = [
        m for m in customer_messages
        if m.created_at < since
    ]

    # رسائل البوت في الفترة الحالية
    bot_messages = db.execute(
        select(
            Message.flag,
            Message.latency_ms,
        ).where(
            Message.company_id == c.id,
            Message.role == "bot",
            Message.created_at >= since,
            Message.created_at < now,
        )
    ).all()

    # المحادثات الجديدة
    new_now = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.company_id == c.id,
            Conversation.created_at >= since,
            Conversation.created_at < now,
        )
    ) or 0

    new_prev = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.company_id == c.id,
            Conversation.created_at >= prev_since,
            Conversation.created_at < since,
        )
    ) or 0

    # المحادثات المفتوحة التي تحتاج موظفًا أو يتولاها موظف
    open_handoffs = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.company_id == c.id,
            Conversation.status.in_(["needs_human", "human"]),
        )
    ) or 0

    # توزيع اللغات
    raw_langs = db.scalars(
        select(Conversation.lang).where(
            Conversation.company_id == c.id,
            Conversation.created_at >= since,
            Conversation.created_at < now,
        )
    ).all()

    langs = Counter(
        str(lang).strip().lower()
        for lang in raw_langs
        if lang
    )

    lang_total = sum(langs.values())

    ar_count = langs.get("ar", 0)
    en_count = langs.get("en", 0)
    other_count = max(0, lang_total - ar_count - en_count)

    def lang_pct(count: int) -> int:
        return round(count * 100 / lang_total) if lang_total else 0

    # أداء البوت
    auto = sum(1 for flag, _ in bot_messages if flag == "auto")
    handoffs = sum(1 for flag, _ in bot_messages if flag == "handoff")

    latencies = [
        latency
        for _, latency in bot_messages
        if latency is not None and latency >= 0
    ]

    avg_latency = (
        round(sum(latencies) / len(latencies) / 1000, 1)
        if latencies else 0
    )

    automation = (
        round(auto * 100 / len(bot_messages), 1)
        if bot_messages else 0
    )

    # توزيع أوقات رسائل العملاء
    buckets = {
        "morning": 0,
        "afternoon": 0,
        "evening": 0,
        "night": 0,
    }

    series = Counter()

    for message in current_messages:
        local_time = _cairo_datetime(message.created_at)
        hour = local_time.hour

        if 6 <= hour < 12:
            buckets["morning"] += 1
        elif 12 <= hour < 18:
            buckets["afternoon"] += 1
        elif 18 <= hour < 24:
            buckets["evening"] += 1
        else:
            buckets["night"] += 1

        series[local_time.date()] += 1

    today = datetime.now(CAIRO).date()

    spark = [
        series.get(today - timedelta(days=i), 0)
        for i in range(days - 1, -1, -1)
    ]

    total_current = len(current_messages)

    def pct(value: int) -> int:
        return round(value * 100 / total_current) if total_current else 0

    # أكثر الأسئلة تكرارًا
    top = Counter(
        normalized
        for message in current_messages
        if (normalized := _norm(message.content))
    ).most_common(5)

    unanswered = Counter(
        normalized
        for message in current_messages
        if message.unanswered
        and (normalized := _norm(message.content))
    ).most_common(5)

    return {
        "messages": total_current,
        "messages_prev": len(previous_messages),

        "automation": automation,
        "answered_auto": auto,
        "bot_total": len(bot_messages),

        "new_customers": new_now,
        "new_customers_delta": new_now - new_prev,

        "avg_latency": avg_latency,

        "handoffs": handoffs,
        "open_handoffs": open_handoffs,

        "top_questions": [
            {"q": question, "n": count}
            for question, count in top
        ],

        "unanswered": [
            {"q": question, "n": count}
            for question, count in unanswered
        ],

        "peak": {
            key: pct(value)
            for key, value in buckets.items()
        },

        "langs": {
            "ar": lang_pct(ar_count),
            "en": lang_pct(en_count),
            "other": lang_pct(other_count),
        },

        "series": spark,
    }
