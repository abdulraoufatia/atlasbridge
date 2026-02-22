"""Safety guard: config schema and safety defaults must not drift."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlasbridge.core.config import AtlasBridgeConfig

# --- Config model fields ---


FROZEN_TOP_LEVEL_FIELDS = frozenset(
    {
        "config_version",
        "telegram",
        "slack",
        "prompts",
        "logging",
        "database",
        "adapters",
    }
)


def test_config_has_frozen_fields():
    """AtlasBridgeConfig must have all frozen top-level fields."""
    actual = set(AtlasBridgeConfig.model_fields.keys())
    missing = FROZEN_TOP_LEVEL_FIELDS - actual
    assert not missing, f"Config fields removed: {sorted(missing)}"


def test_config_version_defaults_to_1():
    """config_version must default to 1."""
    default = AtlasBridgeConfig.model_fields["config_version"].default
    assert default == 1, f"config_version default changed to {default}"


# --- Safety defaults ---


def test_yes_no_safe_default_is_n():
    """PromptsConfig.yes_no_safe_default must default to 'n'."""
    from atlasbridge.core.config import PromptsConfig

    cfg = PromptsConfig()
    assert cfg.yes_no_safe_default == "n", (
        f"SAFETY VIOLATION: yes_no_safe_default changed to '{cfg.yes_no_safe_default}'"
    )


def test_yes_no_safe_default_rejects_y():
    """PromptsConfig.yes_no_safe_default must reject 'y' and 'yes'."""
    from atlasbridge.core.config import PromptsConfig

    with pytest.raises(ValidationError):
        PromptsConfig(yes_no_safe_default="y")

    with pytest.raises(ValidationError):
        PromptsConfig(yes_no_safe_default="yes")


# --- Environment variable overlay ---


FROZEN_ENV_VARS = frozenset(
    {
        "ATLASBRIDGE_TELEGRAM_BOT_TOKEN",
        "ATLASBRIDGE_TELEGRAM_ALLOWED_USERS",
        "ATLASBRIDGE_SLACK_BOT_TOKEN",
        "ATLASBRIDGE_SLACK_APP_TOKEN",
        "ATLASBRIDGE_SLACK_ALLOWED_USERS",
        "ATLASBRIDGE_LOG_LEVEL",
        "ATLASBRIDGE_DB_PATH",
        "ATLASBRIDGE_APPROVAL_TIMEOUT_SECONDS",
    }
)


def test_env_vars_documented_in_apply_env_overrides():
    """_apply_env_overrides must reference all frozen environment variables."""
    import inspect

    from atlasbridge.core.config import _apply_env_overrides

    source = inspect.getsource(_apply_env_overrides)
    for var in FROZEN_ENV_VARS:
        assert var in source, (
            f"Environment variable '{var}' no longer referenced in _apply_env_overrides(). "
            f"Removing env var support is a breaking change."
        )
