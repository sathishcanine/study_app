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
    admin_api_key: str = "change-me-admin-key"
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    vector_dim: int = 1536
    data_root: str = "data"
    rules_dir: str = "data/rules"
    previous_year_dir: str = "data/previous_year"
    materials_dir: str = "data/materials"
    current_affairs_dir: str = "data/current_affairs"


settings = Settings()


def google_client_id_list() -> list[str]:
    return [x.strip() for x in settings.google_client_ids.split(",") if x.strip()]
