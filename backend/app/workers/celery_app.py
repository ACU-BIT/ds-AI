from celery import Celery
from app.config import settings

celery = Celery("teledesk", broker=settings.REDIS_URL, backend=settings.REDIS_URL,
                include=["app.workers.process_document", "app.workers.handle_message"])
celery.conf.task_track_started = True
