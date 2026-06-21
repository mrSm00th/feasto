import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.db.database import AsyncSessionLocal
from app.modules.restaurants.payout_models import (
    RestaurantEarning,
    RestaurantEarningStatus,
)
from app.modules.restaurants.payout_services import (
    initiate_restaurant_payout_transfer,
    run_payout_batch_for_restaurant,
)

logger = logging.getLogger(__name__)

PAYOUT_PERIOD_DAYS = 7


@celery_app.task(name="restaurants.run_weekly_payouts")
def run_weekly_restaurant_payouts() -> None:
    asyncio.run(_run_weekly_restaurant_payouts_async())


async def _run_weekly_restaurant_payouts_async() -> None:
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=PAYOUT_PERIOD_DAYS)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RestaurantEarning.restaurant_id)
            .where(RestaurantEarning.status == RestaurantEarningStatus.PENDING)
            .distinct()
        )
        restaurant_ids = [row[0] for row in result.all()]

    if not restaurant_ids:
        logger.info(
            "Weekly restaurant payout run: no restaurants with pending earnings."
        )
        return

    logger.info(
        "Weekly restaurant payout run: processing %d restaurants.", len(restaurant_ids)
    )

    for restaurant_id in restaurant_ids:
        async with AsyncSessionLocal() as db:
            try:
                payout = await run_payout_batch_for_restaurant(
                    restaurant_id, period_start, period_end, db
                )

                if payout is None:
                    await db.commit()
                    continue

                await initiate_restaurant_payout_transfer(payout, db)
                await db.commit()

                logger.info(
                    "Payout %s created for restaurant %s: ₹%s",
                    payout.id,
                    restaurant_id,
                    payout.total_amount,
                )

            except Exception:
                await db.rollback()
                logger.exception(
                    "Payout batch failed for restaurant %s — will retry next run.",
                    restaurant_id,
                )
