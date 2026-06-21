# riders/payout_schemas.py

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.modules.riders.models import EarningStatus, PayoutStatus


class BaseSchema(BaseModel):

    model_config = ConfigDict(from_attributes=True)


class RiderEarningResponseSchema(BaseSchema):
    id: uuid.UUID
    order_id: uuid.UUID
    amount: Decimal
    status: EarningStatus
    payout_id: uuid.UUID | None
    created_at: datetime


class PayoutResponseSchema(BaseSchema):
    id: uuid.UUID
    total_amount: Decimal
    status: PayoutStatus
    provider_payout_id: str | None
    failure_reason: str | None
    period_start: datetime
    period_end: datetime
    created_at: datetime
    completed_at: datetime | None


class RiderEarningsSummarySchema(BaseSchema):
    pending_amount: Decimal
    total_deliveries: int
    recent_earnings: list[RiderEarningResponseSchema]
    payouts: list[PayoutResponseSchema]


class PayoutListResponseSchema(BaseSchema):
    total: int
    payouts: list[PayoutResponseSchema]
