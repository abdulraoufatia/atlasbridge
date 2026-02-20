"""Aegis configuration: Pydantic model, load, and save."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aegis.core.constants import (
    AEGIS_DIR_NAME,
    AUDIT_FILENAME,
    CONFIG_FILENAME,
    DB_FILENAME,
    DEFAULT_FREE_TEXT_MAX_CHARS,
    DEFAULT_PROMPT_TIMEOUT_SECONDS,
    DEFAULT_STUCK_TIMEOUT_SECONDS,
    LOG_FILENAME,
)
from aegis.core.exceptions import ConfigError, ConfigNotFoundError


def aegis_dir() -> Path:
    """Return the Aegis config directory (~/.aegis), creating it if needed."""
    d = Path.home() / AEGIS_DIR_NAME
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class TelegramConfig(BaseModel):
    bot_token: SecretStr
    allowed_users: list[int] = Field(min_length=1)

    @field_validator("bot_token", mode="before")
    @classmethod
    def validate_token_format(cls, v: Any) -> Any:
        token = str(v.get_secret_value() if hasattr(v, "get_secret_value") else v)
        # Telegram bot tokens look like: 123456789:ABCdef...
        import re

        if not re.fullmatch(r"\d{8,12}:[A-Za-z0-9_\-]{35,}", token):
            raise ValueError(
                "Invalid Telegram bot token format. "
                "Expected: <digits>:<35+ chars>. Get one from @BotFather."
            )
        return v

    @field_validator("allowed_users", mode="before")
    @classmethod
    def parse_allowed_users(cls, v: Any) -> Any:
        """Accept both list and comma-separated string."""
        if isinstance(v, str):
            return [int(uid.strip()) for uid in v.split(",") if uid.strip()]
        return v


class PromptsConfig(BaseModel):
    timeout_seconds: int = DEFAULT_PROMPT_TIMEOUT_SECONDS
    reminder_seconds: int | None = None
    free_text_enabled: bool = False
    free_text_max_chars: int = DEFAULT_FREE_TEXT_MAX_CHARS
    stuck_timeout_seconds: float = DEFAULT_STUCK_TIMEOUT_SECONDS

    # Safe default for yes/no on timeout — "n" is the only allowed value
    yes_no_safe_default: str = "n"

    @field_validator("yes_no_safe_default")
    @classmethod
    def reject_auto_approve(cls, v: str) -> str:
        if v.lower() in ("y", "yes"):
            raise ValueError(
                "yes_no_safe_default cannot be 'y'. "
                "Auto-approving on timeout is prohibited. Use 'n' (default)."
            )
        return v.lower()

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if not (60 <= v <= 3600):
            raise ValueError("timeout_seconds must be between 60 and 3600")
        return v


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "text"  # "text" | "json"

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
        if v.upper() not in allowed:
            raise ValueError(f"Log level must be one of: {allowed}")
        return v.upper()


class DatabaseConfig(BaseModel):
    path: str = ""  # empty → use default


class AdapterClaudeConfig(BaseModel):
    detection_threshold: float = 0.65
    detection_buffer_size: int = 4096
    use_structured_output: bool = True


class AdaptersConfig(BaseModel):
    claude: AdapterClaudeConfig = Field(default_factory=AdapterClaudeConfig)


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class AegisConfig(BaseModel):
    """Root Aegis configuration model."""

    telegram: TelegramConfig
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    adapters: AdaptersConfig = Field(default_factory=AdaptersConfig)

    # Computed paths (not stored in config file)
    _config_path: Path | None = None

    @property
    def db_path(self) -> Path:
        if self.database.path:
            return Path(self.database.path).expanduser()
        return aegis_dir() / DB_FILENAME

    @property
    def audit_path(self) -> Path:
        return aegis_dir() / AUDIT_FILENAME

    @property
    def log_path(self) -> Path:
        return aegis_dir() / LOG_FILENAME


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def _config_file_path() -> Path:
    if env_path := os.environ.get("AEGIS_CONFIG"):
        return Path(env_path)
    return aegis_dir() / CONFIG_FILENAME


def load_config(path: Path | None = None) -> AegisConfig:
    """
    Load AegisConfig from TOML file, overlaid with environment variables.

    Priority (highest to lowest):
      1. Environment variables (AEGIS_*)
      2. Config file (~/.aegis/config.toml)
    """
    import tomllib

    cfg_path = path or _config_file_path()

    if not cfg_path.exists():
        raise ConfigNotFoundError(
            f"Aegis is not configured. Run 'aegis setup' first.\n"
            f"(Config file not found: {cfg_path})"
        )

    try:
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        raise ConfigError(f"Cannot read config file {cfg_path}: {exc}") from exc

    # Apply environment variable overrides
    _apply_env_overrides(data)

    try:
        config = AegisConfig.model_validate(data)
    except Exception as exc:
        raise ConfigError(f"Invalid config at {cfg_path}: {exc}") from exc

    config._config_path = cfg_path
    return config


def _apply_env_overrides(data: dict[str, Any]) -> None:
    """Overlay AEGIS_* environment variables onto the parsed TOML data."""
    if token := os.environ.get("AEGIS_TELEGRAM_BOT_TOKEN"):
        data.setdefault("telegram", {})["bot_token"] = token
    if users := os.environ.get("AEGIS_TELEGRAM_ALLOWED_USERS"):
        data.setdefault("telegram", {})["allowed_users"] = users
    if level := os.environ.get("AEGIS_LOG_LEVEL"):
        data.setdefault("logging", {})["level"] = level
    if db := os.environ.get("AEGIS_DB_PATH"):
        data.setdefault("database", {})["path"] = db
    if timeout := os.environ.get("AEGIS_APPROVAL_TIMEOUT_SECONDS"):
        data.setdefault("prompts", {})["timeout_seconds"] = int(timeout)


def save_config(config_data: dict[str, Any], path: Path | None = None) -> Path:
    """Write config dict to TOML file with secure permissions (0600)."""
    import tomli_w

    cfg_path = path or _config_file_path()
    cfg_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Write atomically
    tmp_path = cfg_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "wb") as f:
            tomli_w.dump(config_data, f)
        tmp_path.rename(cfg_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise ConfigError(f"Cannot write config to {cfg_path}: {exc}") from exc

    # Secure permissions
    cfg_path.chmod(0o600)
    return cfg_path
