import ipaddress
from pathlib import Path
from typing import Union

import yaml
from pydantic import BaseModel, Field, field_validator

from sdc_prioritizer.config.constants import CONFIG_DIR, LOGS_DIR, PROJECT_ROOT


# =============================================================================
#   LogConfig
# =============================================================================
class LogConfig(BaseModel):
    """Logging configuration."""

    log_level: str
    file_log_level: str
    file_log_dir: str
    file_log_max_files: int
    file_log_file_size_mb: int

    @field_validator("log_level", "file_log_level")
    def check_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Unrecognized log level: {v}")
        return v.upper()

    @property
    def resolved_log_dir(self) -> Path:
        """Return absolute path to the log directory, creating it if needed."""
        p = Path(self.file_log_dir)
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p


# =============================================================================
#   ServerConfig
# =============================================================================
class ServerConfig(BaseModel):
    """HTTP server configuration."""

    host: str
    port: int = Field(gt=0, le=65535)

    @field_validator("host")
    def check_host(cls, v: str) -> str:
        try:
            ipaddress.ip_address(v)
        except ValueError as exc:
            raise ValueError("host must be a valid IP address") from exc
        return v


# =============================================================================
#   MongoDBConfig
# =============================================================================
class MongoDBConfig(BaseModel):
    """MongoDB configuration (non-sensitive parts)."""

    database: str
    collection_test_cases: str

    @field_validator("database", "collection_test_cases")
    def check_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("MongoDB database and collection names cannot be empty")
        return v


# =============================================================================
#   PostgreSQLConfig
# =============================================================================
class PostgreSQLConfig(BaseModel):
    """PostgreSQL connection-pool configuration (non-sensitive parts)."""

    pool_min_size: int = Field(ge=1)
    pool_max_size: int = Field(ge=1)


# =============================================================================
#   Config  (root)
# =============================================================================
class Config(BaseModel):
    """Root application configuration loaded from config.yml."""

    server: ServerConfig
    logging: LogConfig
    mongodb: MongoDBConfig
    postgresql: PostgreSQLConfig

    @classmethod
    def load_from_file(cls, file_path: Union[str, Path]) -> "Config":
        """Load and validate configuration from a YAML file.

        Args:
            file_path: Path to config.yml.

        Returns:
            Validated Config instance.
        """
        file_path = Path(file_path)

        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Config file not found: {file_path}")

        with open(file_path, "r") as fh:
            raw = yaml.safe_load(fh)

        return cls(**raw)
