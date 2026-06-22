from decimal import Decimal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str

    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # razor pay fields

    razorpay_key_id: str
    razorpay_key_secret: str
    razorpay_webhook_secret: str

    application_per_page: int = 10

    storage_backend: str = "local"

    # storage_backend: str = "local"
    # s3_public_bucket_name: str = ""
    # s3_private_bucket_name: str = ""
    # s3_region: str = ""
    # s3_endpoint_url: str | None = None
    # s3_access_key_id: SecretStr | None = None
    # s3_secret_access_key: SecretStr | None = None

    max_upload_size_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=1024,
        le=10 * 1024 * 1024,
    )

    max_images_per_restaurant: int = 20
    restaurants_per_page: int = 10
    notifications_per_page: int = 10
    max_dining_menu_images_per_restaurant: int = 50
    max_restaurant_images_per_request: int = 10
    max_restaurant_dining_menu_images_per_request: int = 10
    max_restaurant_food_images_per_request: int = 5

    # used to show already approved cuisines
    # so owner can choose cuisine for his restaurant
    approved_cuisine_names_per_page: int = 10

    # used by the restaurants page (/api/restaurants/)
    #  to get all restaurants in the given city, sort by ratings
    restaurants_per_page: int = 10

    # used by cart module
    menuItems_per_catagory_per_page: int = 10
    menu_categories_per_page: int = 10
    menu_items_per_page: int = 10

    tax_rate: Decimal = Decimal("0.18")

    # celery settings
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    order_response_timeout_minutes: int = 5

    # ferent key
    pii_encryption_key: str

    # auto order cancle if rider not found for N minutes
    rider_assignment_timeout_minutes: int = 10

    # delivery fee settings

    base_delivery_price: float = 20.0
    delivery_free_radius_km: float = 2.0
    delivery_near_rate_per_km: float = 8.0
    delivery_far_threshold_km: float = 5.0
    delivery_far_rate_per_km: float = 12.0
    delivery_max_fee: float = 150.0

    # redis url
    redis_url: str = "redis://localhost:6379/1"  # for caching db=1

    # cache keys

    CACHE_TTL_RESTAURANT_DETAIL = 60
    CACHE_TTL_REVIEWS = 300
    CACHE_TTL_CUISINE_LIST = 3600
    CACHE_TTL_DISH_SEARCH = 60
    CACHE_TTL_DISCOVERY_FEED = 30


settings = Settings()
