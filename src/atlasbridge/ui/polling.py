"""
Polling module — synchronous AppState snapshot for the TUI.

The ``poll_state()`` function is safe to call from Textual worker threads.
It reads config and DB state without blocking the event loop directly.
"""

from __future__ import annotations

from atlasbridge.ui.state import AppState, ChannelStatus, ConfigStatus, DaemonStatus

POLL_INTERVAL_SECONDS: float = 5.0


def poll_state() -> AppState:
    """Return a fresh :class:`AppState` snapshot.

    Failures are swallowed so the TUI never crashes on a bad read.
    """
    config_status = ConfigStatus.NOT_FOUND
    channels: list[ChannelStatus] = []
    daemon_status = DaemonStatus.UNKNOWN
    session_count = 0
    pending_count = 0
    last_error = ""

    # ----------------------------------------------------------------
    # Config
    # ----------------------------------------------------------------
    try:
        from atlasbridge.core.config import _config_file_path, load_config

        cfg_path = _config_file_path()
        if cfg_path.exists():
            cfg = load_config(cfg_path)
            config_status = ConfigStatus.LOADED
            if cfg.telegram:
                channels.append(ChannelStatus(name="telegram", configured=True))
            if getattr(cfg, "slack", None):
                channels.append(ChannelStatus(name="slack", configured=True))
        else:
            config_status = ConfigStatus.NOT_FOUND
    except Exception as exc:  # noqa: BLE001
        config_status = ConfigStatus.ERROR
        last_error = str(exc)

    # ----------------------------------------------------------------
    # Daemon PID
    # ----------------------------------------------------------------
    try:
        from atlasbridge.cli._daemon import _read_pid

        pid = _read_pid()
        if pid is not None:
            import psutil

            daemon_status = DaemonStatus.RUNNING if psutil.pid_exists(pid) else DaemonStatus.STOPPED
        else:
            daemon_status = DaemonStatus.STOPPED
    except Exception:  # noqa: BLE001
        daemon_status = DaemonStatus.UNKNOWN

    # ----------------------------------------------------------------
    # Sessions
    # ----------------------------------------------------------------
    try:
        from atlasbridge.core.constants import _default_data_dir
        from atlasbridge.core.store.database import Database

        db_path = _default_data_dir() / "atlasbridge.db"
        if db_path.exists():
            db = Database(db_path)
            db.connect()
            try:
                rows = db.list_active_sessions()
                session_count = len(rows)
                pending_count = sum(
                    1 for r in rows if dict(r).get("status") in ("routed", "awaiting_reply")
                )
            finally:
                db.close()
    except Exception:  # noqa: BLE001
        pass

    # ----------------------------------------------------------------
    # Version check (cached — effectively free on cache hit)
    # ----------------------------------------------------------------
    update_available = False
    latest_version = ""
    try:
        from atlasbridge.core.version_check import check_version

        vs = check_version()
        update_available = vs.update_available
        latest_version = vs.latest or ""
    except Exception:  # noqa: BLE001
        pass

    return AppState(
        config_status=config_status,
        daemon_status=daemon_status,
        channels=channels,
        session_count=session_count,
        pending_prompt_count=pending_count,
        last_error=last_error,
        update_available=update_available,
        latest_version=latest_version,
    )
