from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SecretStr keeps the key out of logs and reprs.
    riot_api_key: SecretStr = SecretStr("")
    riot_account_region: str = "europe"
    riot_match_region: str = "europe"
    riot_platform_region: str = "euw1"

    sync_queues: list[int] = [420, 440]
    sync_match_count: int = 100
    # Every tracked player is synced this often while the API runs; 0 turns it off.
    auto_sync_minutes: int = 30

    anthropic_api_key: SecretStr = SecretStr("")
    coach_model: str = "claude-opus-5-5"
    coach_effort: str = "medium"
    # The local model, through Ollama. Inside Docker, Ollama on this computer is
    # at host.docker.internal; docker-compose.yml sets that.
    ollama_url: str = "http://localhost:11434"
    local_model: str = "qwen3:4b"

    postgres_user: str = "lolcoach"
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = "lolcoach"
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
