import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.restaurants.models import Restaurant
from app.modules.restaurants.payout_models import (
    RestaurantEarning,
    RestaurantEarningStatus,
    RestaurantPayout,
    RestaurantPayoutStatus,
)


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def create_restaurant_earning(
    restaurant: Restaurant,
    order_id: uuid.UUID,
    gross_amount: Decimal,
    db: AsyncSession,
) -> RestaurantEarning:
    
    commission_amount = _round_money(gross_amount * restaurant.commission_rate)
    net_amount = _round_money(gross_amount - commission_amount)

    earning = RestaurantEarning(
        restaurant_id=restaurant.id,
        order_id=order_id,
        gross_amount=gross_amount,
        commission_rate=restaurant.commission_rate,
        commission_amount=commission_amount,
        net_amount=net_amount,
        status=RestaurantEarningStatus.PENDING,
    )
    db.add(earning)
    return earning


async def get_pending_earnings_total(restaurant_id: uuid.UUID, db: AsyncSession) -> Decimal:
    result = await db.execute(
        select(func.coalesce(func.sum(RestaurantEarning.net_amount), 0)).where(
            RestaurantEarning.restaurant_id == restaurant_id,
            RestaurantEarning.status == RestaurantEarningStatus.PENDING,
        )
    )
    return result.scalar() or Decimal("0.00")


async def get_restaurant_earnings_summary(
    restaurant: Restaurant,
    db: AsyncSession,
    recent_limit: int = 20,
) -> dict:
    pending_total = await get_pending_earnings_total(restaurant.id, db)

    earnings_result = await db.execute(
        select(RestaurantEarning)
        .where(RestaurantEarning.restaurant_id == restaurant.id)
        .order_by(RestaurantEarning.created_at.desc())
        .limit(recent_limit)
    )
    recent_earnings = earnings_result.scalars().all()

    payouts_result = await db.execute(
        select(RestaurantPayout)
        .where(RestaurantPayout.restaurant_id == restaurant.id)
        .order_by(RestaurantPayout.created_at.desc())
        .limit(10)
    )
    payouts = payouts_result.scalars().all()

    return {
        "pending_amount": pending_total,
        "commission_rate": restaurant.commission_rate,
        "recent_earnings": recent_earnings,
        "payouts": payouts,
    }


async def get_restaurant_payouts(
    restaurant: Restaurant,
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[RestaurantPayout], int]:
    count_result = await db.execute(
        select(func.count()).select_from(RestaurantPayout).where(
            RestaurantPayout.restaurant_id == restaurant.id
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(RestaurantPayout)
        .where(RestaurantPayout.restaurant_id == restaurant.id)
        .order_by(RestaurantPayout.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all(), total


async def run_payout_batch_for_restaurant(
    restaurant_id: uuid.UUID,
    period_start: datetime,
    period_end: datetime,
    db: AsyncSession,
) -> RestaurantPayout | None:
    
    result = await db.execute(
        select(RestaurantEarning)
        .where(
            RestaurantEarning.restaurant_id == restaurant_id,
            RestaurantEarning.status == RestaurantEarningStatus.PENDING,
        )
        .with_for_update()
    )
    pending_earnings = result.scalars().all()

    if not pending_earnings:
        return None

    total_net = sum((e.net_amount for e in pending_earnings), Decimal("0.00"))

    payout = RestaurantPayout(
        restaurant_id=restaurant_id,
        total_amount=total_net,
        status=RestaurantPayoutStatus.PENDING,
        period_start=period_start,
        period_end=period_end,
    )
    db.add(payout)
    await db.flush()

    earning_ids = [e.id for e in pending_earnings]
    await db.execute(
        update(RestaurantEarning)
        .where(RestaurantEarning.id.in_(earning_ids))
        .values(status=RestaurantEarningStatus.PAID_OUT, payout_id=payout.id)
    )

    return payout


async def initiate_restaurant_payout_transfer(payout: RestaurantPayout, db: AsyncSession) -> None:
   
    payout.status = RestaurantPayoutStatus.PROCESSING

    # TODO:  RazorpayX payout call

    payout.status = RestaurantPayoutStatus.COMPLETED
    payout.completed_at = datetime.now(UTC)