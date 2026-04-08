from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/study_app"
    secret_key: str = "dev-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    # Comma-separated OAuth 2.0 client IDs (Web + Android + iOS) used to verify Google ID tokens
    google_client_ids: str = (
        "644097932381-jmd5k911215rn19237e5kbapge7qokog.apps.googleusercontent.com"
    )


settings = Settings()


def google_client_id_list() -> list[str]:
    return [x.strip() for x in settings.google_client_ids.split(",") if x.strip()]
