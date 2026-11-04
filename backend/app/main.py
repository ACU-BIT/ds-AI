import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import FRONTEND_DIR
from app.database import init_db
from app.routes import auth, billing, bots, company, conversations, documents, stats, webhooks
from app.services import storage

log = logging.getLogger("teledesk")


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("Initializing database...")
    init_db()

    log.info("Checking MinIO storage...")
    storage.ensure_bucket()

    log.info("TeleDesk startup completed.")
    yield


app = FastAPI(title="TeleDesk", lifespan=lifespan)

for r in (auth, company, documents, bots, conversations, stats, billing):
    app.include_router(r.router, prefix="/api")

app.include_router(webhooks.router)

# الواجهة تتخدم من نفس السيرفر (لازم تتحط آخر حاجة)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")