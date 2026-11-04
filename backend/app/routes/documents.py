
"""رفع وإدارة مستندات الشركات."""

import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import current_company
from app.models import Chunk, Company, Document
from app.services import storage
from app.services.plans import PLANS, usage
from app.workers.process_document import process_document


log = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_BYTES = 10 * 1024 * 1024

KINDS = {
    "pdf": "pdf",
    "docx": "docx",
    "txt": "txt",
    "md": "txt",
}


class TextIn(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    content: str = Field(min_length=10)


def _check_limit(db: Session, company: Company):
    plan = PLANS.get(company.plan)

    if plan is None:
        raise HTTPException(400, "الخطة الحالية غير معروفة")

    limit = plan["files"]

    if limit is not None:
        current_usage = usage(db, company.id, company.plan)

        if current_usage["files"] >= limit:
            raise HTTPException(
                400,
                f"وصلت للحد الأقصى للملفات في خطتك ({limit}). "
                "رقّي الخطة أو احذف ملفات.",
            )


def _dict(document: Document):
    return {
        "id": document.id,
        "name": document.name,
        "kind": document.kind,
        "size": document.size,
        "status": document.status,
        "error": document.error,
        "uses": document.uses,
        "updated_at": (
            document.updated_at.isoformat()
            if document.updated_at
            else None
        ),
    }


@router.get("")
def list_docs(
    company: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    documents = db.scalars(
        select(Document)
        .where(Document.company_id == company.id)
        .order_by(Document.updated_at.desc())
    ).all()

    return {
        "items": [_dict(document) for document in documents],
        "storage_bytes": sum(document.size for document in documents),
    }


def _create(
    db: Session,
    company: Company,
    name: str,
    kind: str,
    data: bytes,
) -> Document:
    if not data:
        raise HTTPException(400, "الملف فارغ")

    if len(data) > MAX_BYTES:
        raise HTTPException(400, "الملف أكبر من 10 ميجا")

    name = (name or "").strip()[:250]

    if not name:
        name = "document"

    if kind not in {"pdf", "docx", "txt"}:
        raise HTTPException(400, "نوع الملف غير مدعوم")

    key = f"{company.id}/{uuid.uuid4().hex}.{kind}"

    # رفع الملف إلى التخزين قبل إنشاء سجل قاعدة البيانات.
    try:
        storage.put(key, data)
    except Exception:
        log.exception("Could not upload document to storage")
        raise HTTPException(
            503,
            "تعذر رفع الملف إلى التخزين. حاول مرة أخرى.",
        )

    try:
        document = Document(
            company_id=company.id,
            name=name,
            kind=kind,
            size=len(data),
            storage_key=key,
        )

        db.add(document)
        db.commit()
        db.refresh(document)

    except Exception:
        db.rollback()

        try:
            storage.delete(key)
        except Exception:
            log.exception(
                "Could not remove orphaned storage file: %s",
                key,
            )

        raise

    # تشغيل المعالجة بعد حفظ المستند.
    try:
        process_document.delay(document.id)

    except Exception as exc:
        log.exception(
            "Could not enqueue document processing: %s",
            document.id,
        )

        document.status = "failed"
        document.error = f"تعذر بدء المعالجة: {str(exc)[:200]}"

        try:
            db.commit()
            db.refresh(document)
        except Exception:
            db.rollback()
            log.exception(
                "Could not save document processing failure: %s",
                document.id,
            )

    return document


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    company: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    filename = (
        (file.filename or "")
        .replace("\\", "/")
        .split("/")[-1]
        .strip()
    )

    if "." not in filename:
        raise HTTPException(
            400,
            "نوع الملف غير مدعوم. الأنواع المسموحة: PDF أو DOCX أو TXT",
        )

    extension = filename.rsplit(".", 1)[-1].lower()

    if extension not in KINDS:
        raise HTTPException(
            400,
            "الأنواع المسموحة: PDF أو Word (docx) أو نص",
        )

    _check_limit(db, company)

    try:
        # نقرأ الحد الأقصى + بايت واحد لاكتشاف الملفات الكبيرة.
        data = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()

    if len(data) > MAX_BYTES:
        raise HTTPException(400, "الملف أكبر من 10 ميجا")

    if not data:
        raise HTTPException(400, "الملف فارغ")

    return _dict(
        _create(
            db,
            company,
            filename,
            KINDS[extension],
            data,
        )
    )


@router.post("/text")
def add_text(
    body: TextIn,
    company: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    title = body.title.strip()
    content = body.content.strip()

    if not title:
        raise HTTPException(400, "اكتب عنوانًا صحيحًا")

    if len(content) < 10:
        raise HTTPException(400, "المحتوى قصير جدًا")

    data = content.encode("utf-8")

    if len(data) > MAX_BYTES:
        raise HTTPException(400, "المحتوى أكبر من 10 ميجا")

    _check_limit(db, company)

    return _dict(
        _create(
            db,
            company,
            title,
            "txt",
            data,
        )
    )


@router.delete("/{doc_id}")
def remove(
    doc_id: int,
    company: Company = Depends(current_company),
    db: Session = Depends(get_db),
):
    document = db.get(Document, doc_id)

    if not document or document.company_id != company.id:
        raise HTTPException(404, "الملف مش موجود")

    key = document.storage_key

    try:
        db.execute(
            delete(Chunk).where(
                Chunk.document_id == document.id,
                Chunk.company_id == company.id,
            )
        )

        db.delete(document)
        db.commit()

    except Exception:
        db.rollback()
        log.exception("Could not delete document from database: %s", doc_id)
        raise

    # حذف الملف من التخزين بعد نجاح الحذف من قاعدة البيانات.
    try:
        storage.delete(key)
    except Exception:
        log.exception(
            "Could not delete storage object for document %s: %s",
            doc_id,
            key,
        )

    return {"ok": True}
