import pytest
from app.services.ingest import NoTextError, chunk_text, extract_text


def test_chunking_respects_size():
    text = "\n\n".join(f"فقرة رقم {i} " + "كلمة " * 60 for i in range(20))
    chunks = chunk_text(text, size=900)
    assert len(chunks) > 1 and all(len(c) <= 1000 for c in chunks)


def test_long_paragraph_is_split():
    assert len(chunk_text("ا" * 3000, size=900)) >= 3


def test_plain_text_extract():
    assert "الشحن" in extract_text("txt", "الشحن داخل القاهرة 50 جنيه والتوصيل يومين".encode())


def test_empty_text_fails():
    with pytest.raises(NoTextError):
        extract_text("txt", b"  ")
