import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.riders.models import (
    EarningStatus,
    Payout,
    Rider,
    RiderEarning,
)


async def create_rider_earning(
    rider_id: uuid.UUID,
    order_id: uuid.UUID,
    amount: Decimal,
    db: AsyncSession,
) -> RiderEarning:

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