from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "Kartflow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Auto-discover tasks in modules — looks for tasks.py in each listed module
celery_app.autodiscover_tasks(["app.modules.orders"])
