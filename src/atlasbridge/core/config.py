"""AtlasBridge configuration: Pydantic model, load, save, and legacy migration."""

from __future__ import annotations

import os
import shutil
import warnings as _warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from atlasbridge.core.constants import (
    AUDIT_FILENAME,
    CONFIG_FILENAME,
    DB_FILENAME,
    DEFAULT_TIMEOUT_SECONDS,
    LEGACY_AEGIS_DIR,
    LOG_FILENAME,
    STUCK_TIMEOUT_SECONDS,
    _default_data_dir,
)
from atlasbridge.core.exceptions import ConfigError, ConfigNotFoundError


def atlasbridge_dir() -> Path:
    """
    Return the AtlasBridge data directory, creating it if needed.

    macOS : ~/Library/Application Support/atlasbridge
    Linux : ~/.config/atlasbridge  (or $XDG_CONFIG_HOME/atlasbridge)
    Other : ~/.atlasbridge

    If a legacy ~/.aegis/ directory exists and no new config is present,
    it is automatically migrated on first call.
    """
    d = _default_data_dir()
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    _maybe_migrate_legacy(d)
    return d


def _maybe_migrate_legacy(new_dir: Path) -> None:
    """
    One-time automatic migration from ~/.aegis/ to the platform-native directory.

    Copies config.toml, the database, and the audit log — then writes a
    migration marker so the migration only runs once.
    """
    marker = new_dir / ".migrated_from_aegis"
    if marker.exists() or not LEGACY_AEGIS_DIR.exists():
        return

    migrated = []
    for filename in (CONFIG_FILENAME, "aegis.db", "audit.log"):
        src = LEGACY_AEGIS_DIR / filename
        if src.exists():
            dst = new_dir / (DB_FILENAME if filename == "aegis.db" else filename)
            try:
                shutil.copy2(src, dst)
                migrated.append(filename)
            except OSError:
                pass  # non-fatal; user can migrate manually

    marker.touch()
    if migrated:
        import structlog

        structlog.get_logger().info(
            "config_migrated_from_aegis",
            target_dir=str(new_dir),
            files=", ".join(migrated),
        )


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class TelegramConfig(BaseModel):
    bot_token: SecretStr
    allowed_users: list[int] = Field(min_length=1)

    @field_validator("bot_token", mode="before")
    @classmethod
    def validate_token_format(cls, v: Any) -> Any:
        import re

        token = str(v.get_secret_value() if hasattr(v, "get_secret_value") else v)
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


class SlackConfig(BaseModel):
    bot_token: SecretStr  # xoxb-* Slack Bot User OAuth Token
    app_token: SecretStr  # xapp-* App-Level Token for Socket Mode
    allowed_users: list[str] = Field(min_length=1)  # Slack user IDs, e.g. "U1234567890"

    @field_validator("bot_token", mode="before")
    @classmethod
    def validate_bot_token(cls, v: Any) -> Any:
        import re

        token = str(v.get_secret_value() if hasattr(v, "get_secret_value") else v)
        if not re.fullmatch(r"xoxb-[A-Za-z0-9\-]+", token):
            raise ValueError(
                "Invalid Slack bot token format. "
                "Expected: xoxb-<alphanumeric>. Get one from your Slack App settings."
            )
        return v

    @field_validator("app_token", mode="before")
    @classmethod
    def validate_app_token(cls, v: Any) -> Any:
        import re

        token = str(v.get_secret_value() if hasattr(v, "get_secret_value") else v)
        if not re.fullmatch(r"xapp-[A-Za-z0-9\-]+", token):
            raise ValueError(
                "Invalid Slack app token format. "
                "Expected: xapp-<alphanumeric>. Enable Socket Mode in your Slack App settings."
            )
        return v


class PromptsConfig(BaseModel):
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    reminder_seconds: int | None = None
    free_text_enabled: bool = False
    free_text_max_chars: int = 200
    stuck_timeout_seconds: float = STUCK_TIMEOUT_SECONDS

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


class StreamingConfig(BaseModel):
    """Configuration for PTY output streaming to channels."""

    batch_interval_s: float = 2.0
    max_output_chars: int = 2000
    max_messages_per_minute: int = 15
    min_meaningful_chars: int = 10
    edit_last_message: bool = True
    redact_secrets: bool = True

    @field_validator("batch_interval_s")
    @classmethod
    def validate_batch_interval(cls, v: float) -> float:
        if not (0.5 <= v <= 30.0):
            raise ValueError("batch_interval_s must be between 0.5 and 30.0")
        return v

    @field_validator("max_messages_per_minute")
    @classmethod
    def validate_rate_limit(cls, v: int) -> int:
        if not (1 <= v <= 60):
            raise ValueError("max_messages_per_minute must be between 1 and 60")
        return v


class ProviderConfig(BaseModel):
    """LLM provider configuration for chat mode."""

    name: str = ""  # anthropic | openai | google
    model: str = ""  # empty = provider default
    api_key: SecretStr | None = None
    max_tokens: int = 4096
    system_prompt: str = ""

    @field_validator("name")
    @classmethod
    def validate_provider_name(cls, v: str) -> str:
        if v and v not in ("anthropic", "openai", "google"):
            raise ValueError(f"Unknown provider {v!r}. Supported: anthropic, openai, google")
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        if not (1 <= v <= 128000):
            raise ValueError("max_tokens must be between 1 and 128000")
        return v


class ChatConfig(BaseModel):
    """Chat mode configuration."""

    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    tools_enabled: bool = True
    max_history_messages: int = 50

    @field_validator("max_history_messages")
    @classmethod
    def validate_max_history(cls, v: int) -> int:
        if not (1 <= v <= 500):
            raise ValueError("max_history_messages must be between 1 and 500")
        return v


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


_VALID_ENVIRONMENTS = frozenset({"dev", "staging", "production"})


class RuntimeConfig(BaseModel):
    """Runtime behaviour settings."""

    model_config = {"extra": "forbid"}

    environment: str = "dev"
    """Runtime environment: dev, staging, or production."""

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v not in _VALID_ENVIRONMENTS:
            raise ValueError(
                f"Invalid environment {v!r}. Must be one of: {sorted(_VALID_ENVIRONMENTS)}"
            )
        return v


class AtlasBridgeConfig(BaseModel):
    """Root AtlasBridge configuration model."""

    config_version: int = 1
    telegram: TelegramConfig | None = None
    slack: SlackConfig | None = None
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    adapters: AdaptersConfig = Field(default_factory=AdaptersConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @model_validator(mode="after")
    def at_least_one_channel(self) -> AtlasBridgeConfig:
        if self.telegram is None and self.slack is None:
            raise ValueError(
                "At least one channel must be configured: [telegram] or [slack]. "
                "Run 'atlasbridge setup' to configure a channel."
            )
        return self

    # Computed paths (not stored in config file)
    _config_path: Path | None = None

    @property
    def db_path(self) -> Path:
        if self.database.path:
            return Path(self.database.path).expanduser()
        return atlasbridge_dir() / DB_FILENAME

    @property
    def audit_path(self) -> Path:
        return atlasbridge_dir() / AUDIT_FILENAME

    @property
    def log_path(self) -> Path:
        return atlasbridge_dir() / LOG_FILENAME


# Backwards-compat alias — remove in v1.0


def __getattr__(name: str) -> type:  # noqa: N807
    if name == "AegisConfig":
        _warnings.warn(
            "AegisConfig is deprecated, use AtlasBridgeConfig instead. Will be removed in v1.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return AtlasBridgeConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def _config_file_path() -> Path:
    # Support both old AEGIS_CONFIG and new ATLASBRIDGE_CONFIG env vars
    if env_path := os.environ.get("ATLASBRIDGE_CONFIG") or os.environ.get("AEGIS_CONFIG"):
        return Path(env_path)
    return atlasbridge_dir() / CONFIG_FILENAME


def load_config(path: Path | str | None = None) -> AtlasBridgeConfig:
    """
    Load AtlasBridgeConfig from TOML file, overlaid with environment variables.

    Priority (highest to lowest):
      1. Environment variables (ATLASBRIDGE_* or legacy AEGIS_*)
      2. Config file (platform data dir / config.toml)

    *path* may be a :class:`~pathlib.Path` or a plain ``str`` — both are accepted.
    """
    import tomllib

    cfg_path = Path(path) if path is not None else _config_file_path()

    if not cfg_path.exists():
        raise ConfigNotFoundError(
            f"AtlasBridge is not configured. Run 'atlasbridge setup' first.\n"
            f"(Config file not found: {cfg_path})"
        )

    try:
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        raise ConfigError(f"Cannot read config file {cfg_path}: {exc}") from exc

    # Auto-migrate old config versions
    from atlasbridge.core.config_migrate import (
        CURRENT_CONFIG_VERSION,
        detect_version,
        upgrade_config,
    )

    detected = detect_version(data)
    if detected < CURRENT_CONFIG_VERSION:
        data = upgrade_config(data, detected, CURRENT_CONFIG_VERSION)
        save_config(data, cfg_path)

    # Resolve keyring placeholders (before env overlays and Pydantic validation)
    _resolve_keyring_placeholders(data)

    # Apply environment variable overrides
    _apply_env_overrides(data)

    try:
        config = AtlasBridgeConfig.model_validate(data)
    except Exception as exc:
        raise ConfigError(f"Invalid config at {cfg_path}: {exc}") from exc

    config._config_path = cfg_path
    return config


def _apply_env_overrides(data: dict[str, Any]) -> None:
    """Overlay ATLASBRIDGE_* (or legacy AEGIS_*) environment variables onto parsed TOML."""

    # New env vars take priority; legacy AEGIS_* are fallbacks for migration
    def _env(*names: str) -> str:
        for name in names:
            v = os.environ.get(name, "")
            if v:
                return v
        return ""

    # Telegram
    if token := _env("ATLASBRIDGE_TELEGRAM_BOT_TOKEN", "AEGIS_TELEGRAM_BOT_TOKEN"):
        data.setdefault("telegram", {})["bot_token"] = token
    if users := _env("ATLASBRIDGE_TELEGRAM_ALLOWED_USERS", "AEGIS_TELEGRAM_ALLOWED_USERS"):
        data.setdefault("telegram", {})["allowed_users"] = users

    # Slack
    if slack_bot := _env("ATLASBRIDGE_SLACK_BOT_TOKEN", "AEGIS_SLACK_BOT_TOKEN"):
        data.setdefault("slack", {})["bot_token"] = slack_bot
    if slack_app := _env("ATLASBRIDGE_SLACK_APP_TOKEN", "AEGIS_SLACK_APP_TOKEN"):
        data.setdefault("slack", {})["app_token"] = slack_app
    if slack_users := _env("ATLASBRIDGE_SLACK_ALLOWED_USERS", "AEGIS_SLACK_ALLOWED_USERS"):
        data.setdefault("slack", {})["allowed_users"] = [
            u.strip() for u in slack_users.split(",") if u.strip()
        ]

    # General
    if level := _env("ATLASBRIDGE_LOG_LEVEL", "AEGIS_LOG_LEVEL"):
        data.setdefault("logging", {})["level"] = level
    if db := _env("ATLASBRIDGE_DB_PATH", "AEGIS_DB_PATH"):
        data.setdefault("database", {})["path"] = db
    if timeout := _env("ATLASBRIDGE_APPROVAL_TIMEOUT_SECONDS", "AEGIS_APPROVAL_TIMEOUT_SECONDS"):
        data.setdefault("prompts", {})["timeout_seconds"] = int(timeout)

    # Chat / LLM provider
    if llm_provider := _env("ATLASBRIDGE_LLM_PROVIDER"):
        data.setdefault("chat", {}).setdefault("provider", {})["name"] = llm_provider
    if llm_key := _env("ATLASBRIDGE_LLM_API_KEY"):
        data.setdefault("chat", {}).setdefault("provider", {})["api_key"] = llm_key
    if llm_model := _env("ATLASBRIDGE_LLM_MODEL"):
        data.setdefault("chat", {}).setdefault("provider", {})["model"] = llm_model

    # Runtime
    if env := _env("ATLASBRIDGE_ENVIRONMENT"):
        data.setdefault("runtime", {})["environment"] = env


def save_config(
    config_data: dict[str, Any],
    path: Path | None = None,
    *,
    use_keyring: bool = False,
) -> Path:
    """Write config dict to TOML file with secure permissions (0600)."""
    import copy

    import tomli_w

    from atlasbridge.core.config_migrate import CURRENT_CONFIG_VERSION

    cfg_path = path or _config_file_path()
    cfg_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Always stamp the current config version
    config_data.setdefault("config_version", CURRENT_CONFIG_VERSION)

    # Optionally migrate tokens to OS keyring
    write_data = config_data
    if use_keyring:
        write_data = copy.deepcopy(config_data)
        _store_tokens_in_keyring(write_data)

    # Write atomically
    tmp_path = cfg_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "wb") as f:
            tomli_w.dump(write_data, f)
        tmp_path.rename(cfg_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise ConfigError(f"Cannot write config to {cfg_path}: {exc}") from exc

    # Secure permissions
    cfg_path.chmod(0o600)
    return cfg_path


# ---------------------------------------------------------------------------
# Keyring helpers
# ---------------------------------------------------------------------------

_KEYRING_TOKEN_FIELDS: list[tuple[str, str]] = [
    ("telegram", "bot_token"),
    ("slack", "bot_token"),
    ("slack", "app_token"),
]

# Nested paths for keyring resolution (section.subsection, key)
_KEYRING_NESTED_FIELDS: list[tuple[str, str, str]] = [
    ("chat", "provider", "api_key"),
]


def _resolve_keyring_placeholders(data: dict[str, Any]) -> None:
    """In-place resolve ``keyring:*`` placeholders to actual tokens."""
    try:
        from atlasbridge.core.keyring_store import is_keyring_placeholder, retrieve_token
    except ImportError:
        return  # keyring extra not installed — nothing to resolve

    for section, key in _KEYRING_TOKEN_FIELDS:
        if section not in data or key not in data[section]:
            continue
        val = data[section][key]
        if is_keyring_placeholder(val):
            resolved = retrieve_token(val)
            if resolved is None:
                raise ConfigError(
                    f"Cannot resolve keyring token for [{section}].{key}. "
                    f"Placeholder: {val!r}. "
                    f"Is the keyring unlocked? Try: pip install 'atlasbridge[keyring]'"
                )
            data[section][key] = resolved

    for section, subsection, key in _KEYRING_NESTED_FIELDS:
        sub = data.get(section, {}).get(subsection, {})
        if key not in sub:
            continue
        val = sub[key]
        if is_keyring_placeholder(val):
            resolved = retrieve_token(val)
            if resolved is None:
                raise ConfigError(
                    f"Cannot resolve keyring token for [{section}.{subsection}].{key}. "
                    f"Placeholder: {val!r}."
                )
            sub[key] = resolved


def _store_tokens_in_keyring(data: dict[str, Any]) -> None:
    """Replace raw token values with keyring placeholders (in-place)."""
    try:
        from atlasbridge.core.keyring_store import is_keyring_available, store_token
    except ImportError:
        return

    if not is_keyring_available():
        return

    for section, key in _KEYRING_TOKEN_FIELDS:
        if section not in data or key not in data[section]:
            continue
        token = data[section][key]
        if isinstance(token, str) and not token.startswith("keyring:"):
            data[section][key] = store_token(f"{section}_{key}", token)
