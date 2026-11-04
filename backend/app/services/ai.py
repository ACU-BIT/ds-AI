"""الكلام مع Gemini. لو عايز تبدّل المزوّد، غيّر الملف ده بس."""

import json
import re

from google.genai import types

from app.config import settings
from app.services.embeddings import client


VALID_HANDOFF_TYPES = {
    "user_request",
    "sensitive",
}


def _parse_response(response_text: str | None) -> dict:
    """تحليل استجابة Gemini والتحقق من شكل البيانات."""

    if not response_text or not response_text.strip():
        raise ValueError("Gemini رجّع استجابة فارغة")

    text = response_text.strip()

    # إزالة علامات Markdown لو النموذج أضافها رغم طلب JSON.
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Gemini رجّع JSON غير صالح") from exc

    # دعم حالة إرجاع قائمة تحتوي على كائن واحد.
    if isinstance(data, list):
        if not data:
            raise ValueError("Gemini رجّع قائمة فارغة")
        data = data[0]

    if not isinstance(data, dict):
        raise ValueError("استجابة Gemini ليست كائن JSON")

    answer = data.get("answer")
    if not isinstance(answer, str):
        answer = ""

    in_scope = data.get("in_scope")
    if not isinstance(in_scope, bool):
        in_scope = False

    needs_human = data.get("needs_human")
    if not isinstance(needs_human, bool):
        needs_human = False

    handoff_type = data.get("handoff_type")

    if handoff_type not in VALID_HANDOFF_TYPES:
        handoff_type = None

    # لو النموذج طلب تحويلًا ولم يحدد نوعه،
    # نترك النوع None حتى يتعامل chat.py معه كتحويل احتياطي.
    source = data.get("source")
    if not isinstance(source, str) or not source.strip():
        source = None
    else:
        source = source.strip()

    reason = data.get("reason")
    if not isinstance(reason, str):
        reason = ""
    else:
        reason = reason.strip()

    return {
        "answer": answer.strip(),
        "in_scope": in_scope,
        "needs_human": needs_human,
        "handoff_type": handoff_type,
        "source": source,
        "reason": reason,
    }


def generate_reply(
    system_prompt: str,
    context: str,
    history: list[dict],
    question: str,
) -> dict:
    """إرسال المحادثة إلى Gemini وإرجاع نتيجة موحدة."""

    contents = []

    for message in history or []:
        if not isinstance(message, dict):
            continue

        content = message.get("content")

        if not isinstance(content, str) or not content.strip():
            continue

        # Gemini يقبل user و model فقط.
        role = (
            "user"
            if message.get("role") == "customer"
            else "model"
        )

        contents.append(
            types.Content(
                role=role,
                parts=[types.Part(text=content)],
            )
        )

    # رسالة العميل الحالية مع معلومات الشركة المسترجعة.
    current_message = (
        f"معلومات الشركة:\n{context}\n\n"
        f"سؤال العميل:\n{question}"
    )

    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=current_message)],
        )
    )

    response = client().models.generate_content(
        model=settings.GEMINI_CHAT_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    return _parse_response(response.text)