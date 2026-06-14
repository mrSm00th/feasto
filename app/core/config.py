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

    dtorage_backend: str = "local"

    # s3_bucket_name: str
    # s3_region: str = "us-west-001"
    # s3_access_key_id: SecretStr | None = None
    # s3_secret_access_key: SecretStr | None = None
    # s3_endpoint_url: str | None = None

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

    # base delivery price - Cart
    base_delivery_price: Decimal = Decimal("50.00")

    tax_rate: Decimal = Decimal("0.18")


settings = Settings()
