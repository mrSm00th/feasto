from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.modules.orders.jobs import auto_cancel_stale_orders

scheduler = AsyncIOScheduler()


def start_scheduler():

    print("Starting APScheduler...")

    scheduler.add_job(
        auto_cancel_stale_orders,
        trigger="interval",
        minutes=1,
        id="auto_cancel_stale_orders",
    )

    scheduler.start()

    print("APScheduler started")
