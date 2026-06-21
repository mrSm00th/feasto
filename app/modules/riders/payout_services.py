import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.riders.models import EarningStatus, RiderEarning


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
