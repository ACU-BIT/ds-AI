
"""إنشاء embeddings باستخدام Gemini."""

import math

from google import genai
from google.genai import types

from app.config import settings


_client = None

BATCH_SIZE = 50
ALLOWED_TASKS = {
    "RETRIEVAL_DOCUMENT",
    "RETRIEVAL_QUERY",
}


def client():
    global _client

    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY غير مضبوط")

        _client = genai.Client(
            api_key=settings.GEMINI_API_KEY
        )

    return _client


def embed(
    texts: list[str],
    task: str = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """
    إنشاء embeddings للنصوص.

    RETRIEVAL_DOCUMENT: لمحتوى الملفات.
    RETRIEVAL_QUERY: لأسئلة العملاء.
    """

    if not texts:
        return []

    if task not in ALLOWED_TASKS:
        raise ValueError(f"نوع embedding غير مدعوم: {task}")

    if not isinstance(texts, list):
        raise TypeError("texts يجب أن تكون قائمة نصوص")

    cleaned_texts = []

    for text in texts:
        if not isinstance(text, str):
            raise TypeError("كل العناصر يجب أن تكون نصوصًا")

        text = text.strip()

        if not text:
            raise ValueError("لا يمكن إنشاء embedding لنص فارغ")

        cleaned_texts.append(text)

    output = []
    expected_dim = int(settings.EMBED_DIM)

    if expected_dim <= 0:
        raise ValueError("EMBED_DIM يجب أن يكون أكبر من صفر")

    for start in range(0, len(cleaned_texts), BATCH_SIZE):
        batch = cleaned_texts[start:start + BATCH_SIZE]

        response = client().models.embed_content(
            model=settings.GEMINI_EMBED_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(
                task_type=task,
                output_dimensionality=expected_dim,
            ),
        )

        embeddings = getattr(response, "embeddings", None)

        if not embeddings or len(embeddings) != len(batch):
            raise ValueError(
                "عدد embeddings المُرجعة لا يطابق عدد النصوص المرسلة"
            )

        for item in embeddings:
            values = getattr(item, "values", None)

            if values is None or len(values) != expected_dim:
                raise ValueError(
                    "أبعاد embedding غير مطابقة لقيمة EMBED_DIM"
                )

            vector = [float(value) for value in values]

            if not all(math.isfinite(value) for value in vector):
                raise ValueError("embedding يحتوي على قيم غير صالحة")

            output.append(vector)

    return output
