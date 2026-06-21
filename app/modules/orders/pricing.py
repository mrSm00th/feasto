from decimal import Decimal

from app.core.config import settings


def calculate_delivery_fee(distance_km: float) -> Decimal:
    """
    Emplementing distance based delivery fee.
     Delivery fee is based on the distance-
         0 - 2 km   : free (covered by base_delivery_price alone)
         2 - 5 km   : per_km_rate per km beyond 2
         5+ km      : higher_per_km_rate per km beyond 5, capped at max_fee
    """
    free_radius_km = Decimal(str(settings.delivery_free_radius_km))
    near_rate = Decimal(str(settings.delivery_near_rate_per_km))
    far_threshold_km = Decimal(str(settings.delivery_far_threshold_km))
    far_rate = Decimal(str(settings.delivery_far_rate_per_km))
    max_fee = Decimal(str(settings.delivery_max_fee))

    distance = Decimal(str(distance_km))

    if distance <= free_radius_km:
        fee = Decimal("0.00")

    elif distance <= far_threshold_km:
        billable_km = distance - free_radius_km
        fee = billable_km * near_rate

    else:
        near_billable_km = far_threshold_km - free_radius_km
        far_billable_km = distance - far_threshold_km
        fee = (near_billable_km * near_rate) + (far_billable_km * far_rate)

    fee = fee.quantize(Decimal("0.01"))
    return min(fee, max_fee)
