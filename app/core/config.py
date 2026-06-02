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
    max_dining_images_per_restaurant: int = 10


settings = Settings()
