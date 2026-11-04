
"""استخراج النصوص وتقسيمها إلى أجزاء مناسبة للبحث الدلالي."""

import io
import re


class NoTextError(Exception):
    """الملف لا يحتوي على نص قابل للقراءة."""


class UnsupportedDocumentError(Exception):
    """نوع الملف غير مدعوم."""


def extract_text(kind: str, data: bytes) -> str:
    if not data:
        raise NoTextError("الملف فارغ")

    kind = (kind or "").lower().strip()

    if kind == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))

        parts = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                parts.append(page_text)

        text = "\n\n".join(parts)

    elif kind == "docx":
        import docx

        document = docx.Document(io.BytesIO(data))
        parts = []

        # استخراج الفقرات.
        for paragraph in document.paragraphs:
            content = paragraph.text.strip()
            if content:
                parts.append(content)

        # استخراج محتوى الجداول.
        for table in document.tables:
            for row in table.rows:
                cells = [
                    cell.text.strip()
                    for cell in row.cells
                    if cell.text.strip()
                ]

                if cells:
                    parts.append(" | ".join(cells))

        text = "\n\n".join(parts)

    elif kind == "txt":
        text = data.decode("utf-8-sig", errors="replace")

    else:
        raise UnsupportedDocumentError(
            f"نوع الملف غير مدعوم: {kind}"
        )

    # تنظيف النص.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    if len(text) < 20:
        raise NoTextError(
            "المستند لا يحتوي على نص كافٍ للمعالجة"
        )

    return text


def chunk_text(
    text: str,
    size: int = 900,
    overlap: int = 150,
) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []

    if size <= 0:
        raise ValueError("size يجب أن يكون أكبر من صفر")

    if overlap < 0 or overlap >= size:
        raise ValueError("overlap يجب أن يكون أصغر من size وغير سالب")

    # تقسيم النص إلى فقرات.
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]

    chunks = []
    current = ""

    def split_long_paragraph(paragraph: str) -> list[str]:
        """تقسيم الفقرة الطويلة مع محاولة الحفاظ على حدود الكلمات."""

        parts = []
        start = 0

        while start < len(paragraph):
            end = min(start + size, len(paragraph))

            if end < len(paragraph):
                boundary = paragraph.rfind(" ", start, end)

                # لا نترك جزءًا صغيرًا جدًا بسبب البحث عن المسافة.
                if boundary > start + size // 2:
                    end = boundary

            piece = paragraph[start:end].strip()

            if piece:
                parts.append(piece)

            if end >= len(paragraph):
                break

            next_start = max(start + 1, end - overlap)

            # منع بداية الجزء التالي داخل كلمة.
            space = paragraph.find(" ", next_start, end)
            if space != -1:
                next_start = space + 1

            start = next_start

        return parts

    for paragraph in paragraphs:
        if len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""

            chunks.extend(split_long_paragraph(paragraph))
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph

        if len(candidate) <= size:
            current = candidate
        else:
            if current:
                chunks.append(current)

            current = paragraph

    if current:
        chunks.append(current)

    return chunks
