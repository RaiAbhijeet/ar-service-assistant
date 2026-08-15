"""Application configuration.

This module is the **only** place in the codebase allowed to read environment
variables directly (via `pydantic-settings`). Every other module must import
`get_settings()` from here. See CLAUDE.md section 7.
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced from the environment / `.env`.

    Field names mirror the variables documented in `.env.example` at the repo
    root. `env_file` lists both a local (`server/.env`) and the repo-root
    (`../.env`) location so this works whether the process is started with
    `cwd == server/` (local dev) or `cwd == repo root` (some tooling); in the
    Docker Compose stack, variables are injected directly and no `.env` file
    needs to be present inside the container.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----------------------------------------------------------- demo object
    arsa_object: str = Field(
        default="bike-drivetrain",
        description="Active demo object; a folder name under objects/.",
    )

    # ------------------------------------------------------------ networking
    arsa_host_ip: str = Field(
        default="127.0.0.1",
        description="LAN IP of the edge server; the headset connects here.",
    )
    arsa_port: int = Field(default=8000, description="Port the API listens on.")

    # ---------------------------------------------------------------- ollama
    ollama_host: str = Field(
        default="http://host.docker.internal:11434",
        description="Base URL of the natively-running Ollama instance on the host.",
    )
    arsa_vlm_model: str = Field(
        default="qwen3-vl:8b", description="Vision-language model tag served by Ollama."
    )
    arsa_embed_model: str = Field(
        default="bge-m3", description="Embedding model tag served by Ollama."
    )

    # ------------------------------------------------------- safety thresholds
    arsa_min_part_confidence: float = Field(
        default=0.65, ge=0.0, le=1.0, description="See ADR-0006."
    )
    arsa_min_retrieval_score: float = Field(
        default=0.35, ge=0.0, le=1.0, description="See ADR-0006."
    )

    # -------------------------------------------------------------- postgres
    postgres_user: str = Field(default="arsa")
    postgres_password: SecretStr = Field(default=SecretStr("change-me-locally"))
    postgres_db: str = Field(default="arsa")
    # Not in .env.example: the compose network resolves the db service by its
    # container DNS name. Overridable for local (non-container) dev.
    postgres_host: str = Field(default="db")
    postgres_port: int = Field(default=5432)

    @property
    def database_dsn(self) -> str:
        """PostgreSQL DSN for asyncpg, built from the fields above."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide `Settings` singleton."""
    return Settings()
