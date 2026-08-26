from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: SecretStr | None = None
    database_url: str = "sqlite+aiosqlite:///./air.db"
    mini_app_url: str | None = None
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    log_level: str = "INFO"
    app_env: str = "development"
    dev_auth_enabled: bool = False
    dev_program_mode: bool = False
    dev_telegram_ids: str = ""
    tester_access_enabled: bool = False
    tester_telegram_ids: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    telegram_init_data_max_age_seconds: int = 86400
    support_url: str | None = None
    terms_url: str | None = None
    privacy_url: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def development_access_enabled(self) -> bool:
        return self.app_env == "development" and self.dev_auth_enabled

    @property
    def program_dev_telegram_ids(self) -> set[int]:
        ids: set[int] = set()
        for raw_id in self.dev_telegram_ids.split(","):
            value = raw_id.strip()
            if value:
                try:
                    ids.add(int(value))
                except ValueError:
                    continue
        return ids

    def is_program_dev(self, telegram_id: int) -> bool:
        return self.dev_program_mode and telegram_id in self.program_dev_telegram_ids

    @property
    def tester_access_telegram_ids(self) -> set[int]:
        ids: set[int] = set()
        for raw_id in self.tester_telegram_ids.split(","):
            value = raw_id.strip()
            if value:
                try:
                    ids.add(int(value))
                except ValueError:
                    continue
        return ids

    def is_tester(self, telegram_id: int) -> bool:
        return self.tester_access_enabled and telegram_id in self.tester_access_telegram_ids

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
