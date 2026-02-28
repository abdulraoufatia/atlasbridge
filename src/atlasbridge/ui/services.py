"""
UI service layer — thin wrappers over existing application functions.

No business logic lives here; every method delegates to the same
functions used by the CLI subcommands (single source of truth).
"""

from __future__ import annotations

from atlasbridge.ui.state import AppState, ConfigStatus, DaemonStatus


class ConfigService:
    """Read AtlasBridge configuration and derive AppState."""

    @staticmethod
    def load_state() -> AppState:
        state = AppState()
        try:
            from atlasbridge.core.config import atlasbridge_dir, load_config

            cfg_path = atlasbridge_dir() / "config.toml"
            if not cfg_path.exists():
                state.config_status = ConfigStatus.NOT_FOUND
                return state
            load_config(str(cfg_path))
            state.config_status = ConfigStatus.LOADED
        except Exception as exc:  # noqa: BLE001
            state.config_status = ConfigStatus.ERROR
            state.last_error = str(exc)
        return state

    @staticmethod
    def is_configured() -> bool:
        try:
            from atlasbridge.core.config import atlasbridge_dir

            return (atlasbridge_dir() / "config.toml").exists()
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def save(config_data: dict) -> str:
        """Save config and return the path as a string."""
        from atlasbridge.core.config import save_config

        path = save_config(config_data)
        return str(path)


class DoctorService:
    """Run environment health checks via the same functions used by `atlasbridge doctor`."""

    @staticmethod
    def run_checks() -> list[dict]:
        from atlasbridge.cli._doctor import (
            _check_bot_token,
            _check_config,
            _check_llm_provider,
            _check_platform,
            _check_poller_lock,
            _check_ptyprocess,
            _check_python_version,
        )

        checks_raw = [
            _check_python_version(),
            _check_platform(),
            _check_ptyprocess(),
            _check_config(),
            _check_bot_token(),
            _check_llm_provider(),
            _check_poller_lock(),
        ]
        return [c for c in checks_raw if c is not None]


class DaemonService:
    """Query and control the AtlasBridge daemon via the same helpers as `atlasbridge start/stop`."""

    @staticmethod
    def get_status() -> DaemonStatus:
        try:
            from atlasbridge.cli._daemon import _pid_alive, _read_pid

            pid = _read_pid()
            if pid is None:
                return DaemonStatus.STOPPED
            return DaemonStatus.RUNNING if _pid_alive(pid) else DaemonStatus.STOPPED
        except Exception:  # noqa: BLE001
            return DaemonStatus.UNKNOWN

    @staticmethod
    def get_pid() -> int | None:
        try:
            from atlasbridge.cli._daemon import _read_pid

            return _read_pid()
        except Exception:  # noqa: BLE001
            return None


class SessionService:
    """List recent AtlasBridge sessions from the SQLite store."""

    @staticmethod
    def list_sessions(limit: int = 20) -> list[dict]:
        try:
            from atlasbridge.core.config import atlasbridge_dir
            from atlasbridge.core.store.database import Database

            db_path = atlasbridge_dir() / "atlasbridge.db"
            if not db_path.exists():
                return []
            db = Database(db_path)
            db.connect()
            rows = db.list_sessions(limit=limit)
            db.close()
            return [dict(r) for r in rows]
        except Exception:  # noqa: BLE001
            return []


class LogsService:
    """Read recent audit log events from the hash-chained audit log."""

    @staticmethod
    def read_recent(limit: int = 100) -> list[dict]:
        try:
            from atlasbridge.core.config import atlasbridge_dir
            from atlasbridge.core.store.database import Database

            db_path = atlasbridge_dir() / "atlasbridge.db"
            if not db_path.exists():
                return []
            db = Database(db_path)
            db.connect()
            try:
                events = db.get_recent_audit_events(limit=limit)
                return [dict(e) for e in events]
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            return []
