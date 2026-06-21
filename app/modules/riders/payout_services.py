# riders/payout_service.py

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.riders.models import (
    EarningStatus,
    Payout,
    PayoutStatus,
    Rider,
    RiderEarning,
)


async def create_rider_earning(
    rider_id: uuid.UUID,
    order_id: uuid.UUID,
    amount: Decimal,
    db: AsyncSession,
) -> RiderEarning:
    """
    Called from mark_order_delivered() at the moment a delivery
    completes. Does not commit — caller's transaction owns that,
    so the earning record and the order's DELIVERED transition
    land atomically together.
    """
    earning = RiderEarning(
        rider_id=rider_id,
        order_id=order_id,
        amount=amount,
        status=EarningStatus.PENDING,
    )
    db.add(earning)
    return earning


async def get_pending_earnings_total(rider_id: uuid.UUID, db: AsyncSession) -> Decimal:
    result = await db.execute(
        select(func.coalesce(func.sum(RiderEarning.amount), 0)).where(
            RiderEarning.rider_id == rider_id,
            RiderEarning.status == EarningStatus.PENDING,
        )
    )
    return result.scalar() or Decimal("0.00")


async def get_rider_earnings_summary(
    rider: Rider,
    db: AsyncSession,
    recent_limit: int = 20,
) -> dict:
    """Used by GET /rider/earnings — pending balance + recent activity."""
    pending_total = await get_pending_earnings_total(rider.id, db)

    earnings_result = await db.execute(
        select(RiderEarning)
        .where(RiderEarning.rider_id == rider.id)
        .order_by(RiderEarning.created_at.desc())
        .limit(recent_limit)
    )
    recent_earnings = earnings_result.scalars().all()

    payouts_result = await db.execute(
        select(Payout)
        .where(Payout.rider_id == rider.id)
        .order_by(Payout.created_at.desc())
        .limit(10)
    )
    payouts = payouts_result.scalars().all()

    return {
        "pending_amount": pending_total,
        "total_deliveries": rider.total_deliveries,
        "recent_earnings": recent_earnings,
        "payouts": payouts,
    }


async def get_rider_payouts(
    rider: Rider,
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Payout], int]:
    count_result = await db.execute(
        select(func.count()).select_from(Payout).where(Payout.rider_id == rider.id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Payout)
        .where(Payout.rider_id == rider.id)
        .order_by(Payout.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all(), total


async def run_payout_batch_for_rider(
    rider_id: uuid.UUID,
    period_start: datetime,
    period_end: datetime,
    db: AsyncSession,
) -> Payout | None:
    """
    Atomically sweeps all PENDING earnings for a rider into one Payout
    row. Uses SELECT FOR UPDATE on the earning rows to prevent a race
    where a delivery completes (creating a new PENDING earning) at the
    exact moment this batch job runs — the lock ensures we get a
    consistent snapshot.

    Returns None if the rider has no pending earnings (nothing to pay out).
    """
    result = await db.execute(
        select(RiderEarning)
        .where(
            RiderEarning.rider_id == rider_id,
            RiderEarning.status == EarningStatus.PENDING,
        )
        .with_for_update()
    )
    pending_earnings = result.scalars().all()

    if not pending_earnings:
        return None

    total_amount = sum((e.amount for e in pending_earnings), Decimal("0.00"))

    payout = Payout(
        rider_id=rider_id,
        total_amount=total_amount,
        status=PayoutStatus.PENDING,
        period_start=period_start,
        period_end=period_end,
    )
    db.add(payout)
    await db.flush()  # get payout.id before reassigning earnings

    earning_ids = [e.id for e in pending_earnings]
    await db.execute(
        update(RiderEarning)
        .where(RiderEarning.id.in_(earning_ids))
        .values(status=EarningStatus.PAID_OUT, payout_id=payout.id)
    )

    return payout


async def initiate_payout_transfer(payout: Payout, db: AsyncSession) -> None:

    payout.status = PayoutStatus.PROCESSING

    # real integration —
    # response = await asyncio.to_thread(
    #     razorpayx_client.payout.create,
    #     {
    #         "account_number": settings.razorpayx_account_number,
    #         "fund_account_id": rider.fund_account_id,  # requires bank
    #                                                      # details collection,
    #                                                      # not yet built
    #         "amount": int(payout.total_amount * 100),
    #         "currency": "INR",
    #         "mode": "UPI",
    #         "purpose": "payout",
    #     }
    # )
    # payout.provider_payout_id = response["id"]

    # Stub completion , for dev purpose
    payout.status = PayoutStatus.COMPLETED
    payout.completed_at = datetime.now(UTC)
