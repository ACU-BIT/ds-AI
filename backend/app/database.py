
"""إعداد اتصال قاعدة البيانات وتهيئة الجداول."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def init_db():
    """تفعيل pgvector وإنشاء الجداول."""

    with engine.begin() as conn:
        conn.execute(
            text("CREATE EXTENSION IF NOT EXISTS vector")
        )

    # تحميل الموديلات قبل إنشاء الجداول.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
