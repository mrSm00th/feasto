from celery import Celery
from celery.schedules import crontab

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

celery_app.conf.beat_schedule = {
    "weekly-rider-payouts": {
        "task": "riders.run_weekly_payouts",
        "schedule": crontab(day_of_week=1, hour=3, minute=0),  # Monday 3 AM
    },
}

# Auto-discover tasks in modules by looking for tasks.py in each listed module
celery_app.autodiscover_tasks(["app.modules.orders"])
