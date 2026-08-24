from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "ArcaCore"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    API_PREFIX: str = "/api"

    class Config:
        env_file = ".env"


settings = Settings()