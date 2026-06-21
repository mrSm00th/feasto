from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.modules.riders.models import Rider
from app.modules.riders.payout_schemas import (
    PayoutListResponseSchema,
    RiderEarningsSummarySchema,
)
from app.modules.riders.payout_services import (
    get_rider_earnings_summary,
    get_rider_payouts,
)
from app.modules.riders.router import get_current_rider   # reuse existing dependency

router = APIRouter(prefix="/rider", tags=["rider-earnings"])


@router.get("/earnings", response_model=RiderEarningsSummarySchema)
async def get_my_earnings(
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    
    summary = await get_rider_earnings_summary(rider, db)
    return RiderEarningsSummarySchema(**summary)


@router.get("/payouts", response_model=PayoutListResponseSchema)
async def get_my_payouts(
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    
    payouts, total = await get_rider_payouts(rider, db, skip, limit)
    return PayoutListResponseSchema(total=total, payouts=payouts)