
"""البحث في مستندات الشركة باستخدام التشابه الدلالي."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.services.embeddings import embed


DEFAULT_K = 5
MAX_K = 20


def search(
    db: Session,
    company_id: int,
    query: str,
    k: int = DEFAULT_K,
) -> list[dict]:
    """إرجاع أقرب أجزاء المستندات التابعة للشركة فقط."""

    if not isinstance(query, str) or not query.strip():
        return []

    if not isinstance(company_id, int) or company_id <= 0:
        return []

    k = max(1, min(int(k), MAX_K))

    # تحويل السؤال إلى embedding.
    vectors = embed([query.strip()], "RETRIEVAL_QUERY")

    if not vectors or vectors[0] is None:
        return []

    query_vector = vectors[0]

    # حساب المسافة الدلالية.
    distance = Chunk.embedding.cosine_distance(query_vector)

    statement = (
        select(
            Chunk.content,
            Document.name,
            distance.label("distance"),
        )
        .join(
            Document,
            Document.id == Chunk.document_id,
        )
        .where(
            Chunk.company_id == company_id,
            Document.company_id == company_id,
            Document.status == "ready",
        )
        .order_by(distance)
        .limit(k)
    )

    rows = db.execute(statement).all()

    results = []

    for content, source, score in rows:
        if not content:
            continue

        results.append({
            "text": content,
            "source": source,
            "distance": float(score) if score is not None else None,
        })

    return results
