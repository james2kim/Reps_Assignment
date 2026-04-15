from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    database_url: str = "postgresql://postgres:postgres@localhost:5432/bigspring"
    sql_echo: bool = False
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    embedding_model: str = "all-MiniLM-L6-v2"
    data_dir: Path = Path("./data")
    log_level: str = "INFO"

    @property
    def database_dir(self) -> Path:
        return self.data_dir / "database"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def raw_assets_dir(self) -> Path:
        return self.data_dir / "raw_assets"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
