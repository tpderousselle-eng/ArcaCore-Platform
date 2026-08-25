from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "ArcaCore"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    API_PREFIX: str = "/api"

    DATABASE_URL: str

    # JWT
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()