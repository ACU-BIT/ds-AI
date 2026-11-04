
"""معالجة المستندات واستخراج النص وإنشاء embeddings."""

import logging
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Chunk, Document
from app.services import storage
from app.services.embeddings import embed
from app.services.ingest import NoTextError, chunk_text, extract_text
from app.workers.celery_app import celery

log = logging.getLogger(__name__)


@celery.task(name="process_document")
def process_document(doc_id: int):
    with SessionLocal() as db:
        doc = db.get(Document, doc_id)

        if not doc:
            log.warning("Document %s not found", doc_id)
            return

        try:
            # 1. استخراج النص من الملف.
            file_content = storage.get(doc.storage_key)
            extracted_text = extract_text(doc.kind, file_content)

            # 2. تقسيم النص إلى أجزاء.
            chunks = chunk_text(extracted_text)

            if not chunks:
                raise NoTextError("المستند لا يحتوي على نص قابل للمعالجة")

            # 3. إنشاء embeddings.
            vectors = embed(chunks, "RETRIEVAL_DOCUMENT")

            # التأكد من وجود متجه لكل جزء.
            if len(chunks) != len(vectors):
                raise ValueError(
                    f"عدد الأجزاء ({len(chunks)}) "
                    f"لا يطابق عدد المتجهات ({len(vectors)})"
                )

            # 4. استبدال الأجزاء القديمة بالجديدة.
            db.query(Chunk).filter(
                Chunk.document_id == doc.id,
                Chunk.company_id == doc.company_id,
            ).delete(synchronize_session=False)

            new_chunks = [
                Chunk(
                    company_id=doc.company_id,
                    document_id=doc.id,
                    content=content,
                    embedding=vector,
                )
                for content, vector in zip(chunks, vectors)
            ]

            db.add_all(new_chunks)

            # 5. تحديث حالة المستند.
            doc.status = "ready"
            doc.error = ""
            doc.updated_at = datetime.now(timezone.utc)

            db.commit()

            log.info(
                "Document %s processed successfully: %s chunks",
                doc_id,
                len(new_chunks),
            )

        except NoTextError as exc:
            db.rollback()

            doc = db.get(Document, doc_id)
            if not doc:
                return

            doc.status = "failed"
            doc.error = str(exc)[:300]
            doc.updated_at = datetime.now(timezone.utc)
            db.commit()

            log.warning("Document %s has no extractable text", doc_id)

        except Exception as exc:
            db.rollback()
            log.exception("Document %s processing failed", doc_id)

            doc = db.get(Document, doc_id)
            if not doc:
                return

            doc.status = "failed"
            doc.error = str(exc)[:300]
            doc.updated_at = datetime.now(timezone.utc)
            db.commit()
