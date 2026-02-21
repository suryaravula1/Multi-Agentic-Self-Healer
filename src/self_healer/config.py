from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SELF_HEALER_",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", validation_alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")

    auto_execute: bool = False
    max_recovery_steps: int = 5
    command_timeout_seconds: int = 30

    sandbox_image: str = "self-healer-sandbox:latest"
    sandbox_memory_limit: str = "256m"
    sandbox_cpu_quota: int = 50_000
    sandbox_network_disabled: bool = True
    sandbox_read_only_root: bool = True

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key.strip())


settings = Settings()
