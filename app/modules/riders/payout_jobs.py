import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.db.database import AsyncSessionLocal
from app.modules.riders.models import EarningStatus, Rider, RiderEarning
from app.modules.riders.payout_services import (
    initiate_payout_transfer,
    run_payout_batch_for_rider,
)

logger = logging.getLogger(__name__)

PAYOUT_PERIOD_DAYS = 7


@celery_app.task(name="riders.run_weekly_payouts")
def run_weekly_payouts() -> None:

    asyncio.run(_run_weekly_payouts_async())


async def _run_weekly_payouts_async() -> None:
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=PAYOUT_PERIOD_DAYS)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RiderEarning.rider_id)
            .where(RiderEarning.status == EarningStatus.PENDING)
            .distinct()
        )
        rider_ids = [row[0] for row in result.all()]

    if not rider_ids:
        logger.info("Weekly payout run: no riders with pending earnings.")
        return

    logger.info("Weekly payout run: processing %d riders.", len(rider_ids))

    for rider_id in rider_ids:
        async with AsyncSessionLocal() as db:
            try:
                payout = await run_payout_batch_for_rider(
                    rider_id, period_start, period_end, db
                )

                if payout is None:
                    await db.commit()
                    continue

                await initiate_payout_transfer(payout, db)
                await db.commit()

                logger.info(
                    "Payout %s created for rider %s: ₹%s",
                    payout.id,
                    rider_id,
                    payout.total_amount,
                )

            except Exception:
                await db.rollback()
                logger.exception(
                    "Payout batch failed for rider %s — will retry next run.",
                    rider_id,
                )
