"""atlasbridge doctor — environment and configuration health check."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.command("doctor")
@click.option("--fix", is_flag=True, default=False, help="Auto-repair fixable issues")
@click.option("--json", "as_json", is_flag=True, default=False)
def doctor_cmd(fix: bool, as_json: bool) -> None:
    """Environment and configuration health check."""
    cmd_doctor(fix=fix, as_json=as_json, console=console)


def _check_python_version() -> dict:
    ver = sys.version_info
    ok = ver >= (3, 11)
    return {
        "name": "Python version",
        "status": "pass" if ok else "fail",
        "detail": f"{ver.major}.{ver.minor}.{ver.micro}" + ("" if ok else " (3.11+ required)"),
    }


def _check_platform() -> dict:
    plat = sys.platform
    supported = plat in ("darwin", "linux") or plat.startswith("linux")
    if supported:
        return {"name": "Platform", "status": "pass", "detail": plat}
    if plat == "win32":
        return {
            "name": "Platform",
            "status": "warn",
            "detail": "Windows (experimental — use --experimental flag, WSL2 recommended)",
        }
    return {"name": "Platform", "status": "warn", "detail": f"{plat} (unsupported)"}


def _check_ptyprocess() -> dict:
    try:
        import ptyprocess  # noqa: F401

        return {"name": "ptyprocess", "status": "pass", "detail": "installed"}
    except ImportError:
        return {
            "name": "ptyprocess",
            "status": "fail",
            "detail": "not installed — run: pip install ptyprocess",
        }


def _config_path() -> Path:
    """Return the canonical config file path (respects ATLASBRIDGE_CONFIG env var)."""
    from atlasbridge.core.config import _config_file_path

    result = _config_file_path()
    # Ensure we always return a Path, even if upstream returns a string
    return Path(result) if not isinstance(result, Path) else result


def _check_config() -> dict:
    try:
        from atlasbridge.core.config import load_config

        cfg_path = _config_path()
        if not cfg_path.exists():
            return {
                "name": "Config file",
                "status": "warn",
                "detail": f"not found at {cfg_path} — run: atlasbridge setup",
            }
        load_config(cfg_path)
        return {"name": "Config file", "status": "pass", "detail": str(cfg_path)}
    except Exception as exc:  # noqa: BLE001
        return {"name": "Config file", "status": "fail", "detail": str(exc)}


def _check_bot_token() -> dict:
    try:
        from atlasbridge.core.config import load_config

        cfg_path = _config_path()
        if not cfg_path.exists():
            return {"name": "Bot token", "status": "skip", "detail": "no config file"}
        cfg = load_config(cfg_path)
        token_obj = cfg.telegram.bot_token if cfg.telegram else None
        if token_obj is None:
            return {
                "name": "Bot token",
                "status": "warn",
                "detail": "not configured — run: atlasbridge setup",
            }
        token = token_obj.get_secret_value()
        masked = token[:8] + "..." + token[-4:]
        return {"name": "Bot token", "status": "pass", "detail": masked}
    except Exception as exc:  # noqa: BLE001
        return {"name": "Bot token", "status": "fail", "detail": str(exc)}


def _check_telegram_reachability() -> dict | None:
    """Verify the configured Telegram bot token can reach the API."""
    try:
        from atlasbridge.core.config import load_config

        cfg_path = _config_path()
        if not cfg_path.exists():
            return None
        cfg = load_config(cfg_path)
        if not cfg.telegram:
            return None
        token = cfg.telegram.bot_token.get_secret_value()

        from atlasbridge.channels.telegram.verify import verify_telegram_token

        ok, detail = verify_telegram_token(token)
        return {
            "name": "Telegram reachability",
            "status": "pass" if ok else "warn",
            "detail": detail,
        }
    except Exception:  # noqa: BLE001
        return None


def _check_systemd() -> dict | None:
    """Linux-only: check if systemd user session is available."""
    if not sys.platform.startswith("linux"):
        return None
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return {
            "name": "systemd (Linux)",
            "status": "warn",
            "detail": "systemctl not found — daemon integration unavailable",
        }
    from atlasbridge.os.systemd.service import is_systemd_available

    if is_systemd_available():
        return {"name": "systemd (Linux)", "status": "pass", "detail": "user session available"}
    return {
        "name": "systemd (Linux)",
        "status": "warn",
        "detail": "systemd not running (container? WSL?) — daemon integration unavailable",
    }


def _check_ui_assets() -> dict:
    """Verify that TUI CSS assets are loadable via importlib.resources."""
    try:
        from importlib.resources import files

        css = files("atlasbridge.ui.css").joinpath("atlasbridge.tcss").read_text("utf-8")
        if len(css) < 10:
            return {
                "name": "UI assets",
                "status": "fail",
                "detail": "atlasbridge.tcss is empty — reinstall: pip install -U atlasbridge",
            }
        return {"name": "UI assets", "status": "pass", "detail": "atlasbridge.tcss loaded OK"}
    except Exception:  # noqa: BLE001
        return {
            "name": "UI assets",
            "status": "fail",
            "detail": "cannot load atlasbridge.tcss — reinstall: pip install -U atlasbridge",
        }


def _check_poller_lock() -> dict | None:
    """Check for stale Telegram poller lock files."""
    try:
        from atlasbridge.core.config import load_config

        cfg_path = _config_path()
        if not cfg_path.exists():
            return None
        cfg = load_config(cfg_path)
        if not cfg.telegram:
            return None
        token = cfg.telegram.bot_token.get_secret_value()
        from atlasbridge.core.poller_lock import check_stale_lock

        return check_stale_lock(token)
    except Exception:  # noqa: BLE001
        return None


def _check_systemd_service() -> dict | None:
    """Linux-only: check if the atlasbridge.service unit is installed."""
    if not sys.platform.startswith("linux"):
        return None
    from atlasbridge.os.systemd.service import systemd_user_dir

    unit_path = systemd_user_dir() / "atlasbridge.service"
    if unit_path.exists():
        return {"name": "atlasbridge.service", "status": "pass", "detail": str(unit_path)}
    return {
        "name": "atlasbridge.service",
        "status": "warn",
        "detail": "not installed — run: atlasbridge setup --install-service",
    }


def _fix_config(console: Console) -> None:
    """Create a config from env vars if available, or a skeleton template."""
    import os
    import re

    cfg_path = _config_path()
    if cfg_path.exists():
        return

    def _env(*names: str) -> str:
        for name in names:
            v = os.environ.get(name, "")
            if v:
                return v
        return ""

    config_data: dict = {}

    # Try Telegram env vars
    tg_token = _env("ATLASBRIDGE_TELEGRAM_BOT_TOKEN", "AEGIS_TELEGRAM_BOT_TOKEN")
    tg_users = _env("ATLASBRIDGE_TELEGRAM_ALLOWED_USERS", "AEGIS_TELEGRAM_ALLOWED_USERS")
    if tg_token and tg_users:
        try:
            users_list = [int(u.strip()) for u in tg_users.split(",") if u.strip()]
            if users_list and re.fullmatch(r"\d{8,12}:[A-Za-z0-9_\-]{35,}", tg_token.strip()):
                config_data["telegram"] = {
                    "bot_token": tg_token.strip(),
                    "allowed_users": users_list,
                }
        except ValueError:
            pass

    # Try Slack env vars
    slack_bot = _env("ATLASBRIDGE_SLACK_BOT_TOKEN", "AEGIS_SLACK_BOT_TOKEN")
    slack_app = _env("ATLASBRIDGE_SLACK_APP_TOKEN", "AEGIS_SLACK_APP_TOKEN")
    slack_users = _env("ATLASBRIDGE_SLACK_ALLOWED_USERS", "AEGIS_SLACK_ALLOWED_USERS")
    if slack_bot and slack_app and slack_users:
        parsed = [u.strip() for u in slack_users.split(",") if u.strip()]
        bot_ok = re.fullmatch(r"xoxb-[A-Za-z0-9\-]+", slack_bot)
        app_ok = re.fullmatch(r"xapp-[A-Za-z0-9\-]+", slack_app)
        if parsed and bot_ok and app_ok:
            config_data["slack"] = {
                "bot_token": slack_bot,
                "app_token": slack_app,
                "allowed_users": parsed,
            }

    if config_data:
        from atlasbridge.core.config import save_config

        try:
            save_config(config_data, cfg_path)
            console.print(
                f"  [green]FIX[/green]  Created config from environment variables at {cfg_path}"
            )
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [red]ERR[/red]  Cannot write config: {exc}")
    else:
        try:
            cfg_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            cfg_path.write_text(
                "# AtlasBridge configuration\n"
                "# Option 1: Edit this file, then run: atlasbridge setup\n"
                "# Option 2: Set env vars, then run: atlasbridge setup --from-env\n"
                "#   ATLASBRIDGE_TELEGRAM_BOT_TOKEN, ATLASBRIDGE_TELEGRAM_ALLOWED_USERS\n\n"
                "config_version = 1\n\n"
                "[telegram]\n"
                '# bot_token = "<YOUR_BOT_TOKEN>"\n'
                "# allowed_users = [<YOUR_TELEGRAM_USER_ID>]\n",
                encoding="utf-8",
            )
            cfg_path.chmod(0o600)
            console.print(f"  [green]FIX[/green]  Created config skeleton at {cfg_path}")
            console.print(
                "          Edit the file or set env vars, then run: atlasbridge doctor --fix"
            )
        except OSError as exc:
            console.print(f"  [red]ERR[/red]  Cannot create config at {cfg_path}: {exc}")


def _fix_database(console: Console) -> None:
    """Create the database and run migrations if needed."""
    from atlasbridge.core.config import atlasbridge_dir
    from atlasbridge.core.constants import DB_FILENAME

    db_path = atlasbridge_dir() / DB_FILENAME
    try:
        import sqlite3

        from atlasbridge.core.store.migrations import (
            LATEST_SCHEMA_VERSION,
            get_user_version,
            run_migrations,
        )

        db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        try:
            version = get_user_version(conn)
            if version < LATEST_SCHEMA_VERSION:
                run_migrations(conn, db_path)
                console.print(
                    f"  [green]FIX[/green]  Database migrated v{version} → v{LATEST_SCHEMA_VERSION} at {db_path}"
                )
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [red]ERR[/red]  Database fix failed: {exc}")


def _fix_stale_pid(console: Console) -> None:
    """Remove stale daemon PID files if the process is no longer alive."""
    import os
    import signal

    from atlasbridge.core.config import atlasbridge_dir

    pid_path = atlasbridge_dir() / "daemon.pid"
    if not pid_path.exists():
        return

    try:
        pid_text = pid_path.read_text().strip()
        if not pid_text.isdigit():
            pid_path.unlink(missing_ok=True)
            console.print(f"  [green]FIX[/green]  Removed malformed PID file at {pid_path}")
            return

        pid = int(pid_text)
        try:
            os.kill(pid, signal.SIG_DFL)
            # Process is alive — do not touch
        except ProcessLookupError:
            pid_path.unlink(missing_ok=True)
            console.print(f"  [green]FIX[/green]  Removed stale PID file (pid {pid} not running)")
        except PermissionError:
            pass  # Process exists but owned by another user — leave it
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [red]ERR[/red]  PID cleanup failed: {exc}")


def _fix_permissions(console: Console) -> None:
    """Repair config file and directory permissions to secure defaults."""
    import stat

    cfg_path = _config_path()
    if not cfg_path.exists():
        return

    try:
        # Config directory should be 0700
        cfg_dir = cfg_path.parent
        dir_mode = stat.S_IMODE(cfg_dir.stat().st_mode)
        if dir_mode & 0o077:  # group or other bits set
            cfg_dir.chmod(0o700)
            console.print(f"  [green]FIX[/green]  Config dir permissions set to 0700: {cfg_dir}")

        # Config file should be 0600
        file_mode = stat.S_IMODE(cfg_path.stat().st_mode)
        if file_mode & 0o077:
            cfg_path.chmod(0o600)
            console.print(f"  [green]FIX[/green]  Config file permissions set to 0600: {cfg_path}")
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [red]ERR[/red]  Permission fix failed: {exc}")


def _check_stale_pid() -> dict | None:
    """Check for stale daemon PID files."""
    import os
    import signal

    try:
        from atlasbridge.core.config import atlasbridge_dir

        pid_path = atlasbridge_dir() / "daemon.pid"
        if not pid_path.exists():
            return None

        pid_text = pid_path.read_text().strip()
        if not pid_text.isdigit():
            return {
                "name": "Daemon PID",
                "status": "warn",
                "detail": f"malformed PID file at {pid_path} — run: atlasbridge doctor --fix",
            }

        pid = int(pid_text)
        try:
            os.kill(pid, signal.SIG_DFL)
            return {
                "name": "Daemon PID",
                "status": "pass",
                "detail": f"daemon running (pid {pid})",
            }
        except ProcessLookupError:
            return {
                "name": "Daemon PID",
                "status": "warn",
                "detail": f"stale PID file (pid {pid} not running) — run: atlasbridge doctor --fix",
            }
        except PermissionError:
            return {
                "name": "Daemon PID",
                "status": "pass",
                "detail": f"daemon running (pid {pid}, different user)",
            }
    except Exception:  # noqa: BLE001
        return None


def _check_permissions() -> dict | None:
    """Check config file and directory permissions."""
    import stat

    try:
        cfg_path = _config_path()
        if not cfg_path.exists():
            return None

        issues: list[str] = []
        dir_mode = stat.S_IMODE(cfg_path.parent.stat().st_mode)
        if dir_mode & 0o077:
            issues.append(f"dir {oct(dir_mode)} (should be 0700)")

        file_mode = stat.S_IMODE(cfg_path.stat().st_mode)
        if file_mode & 0o077:
            issues.append(f"file {oct(file_mode)} (should be 0600)")

        if issues:
            return {
                "name": "Config permissions",
                "status": "warn",
                "detail": ", ".join(issues) + " — run: atlasbridge doctor --fix",
            }
        return {
            "name": "Config permissions",
            "status": "pass",
            "detail": "config dir 0700, config file 0600",
        }
    except Exception:  # noqa: BLE001
        return None


def _check_database() -> dict:
    """Check that the SQLite database is accessible and at the correct schema version."""
    try:
        from atlasbridge.core.config import atlasbridge_dir
        from atlasbridge.core.constants import DB_FILENAME

        db_path = atlasbridge_dir() / DB_FILENAME
        if not db_path.exists():
            return {
                "name": "Database",
                "status": "pass",
                "detail": f"no database yet (will be created on first run): {db_path}",
            }

        import sqlite3

        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        try:
            from atlasbridge.core.store.migrations import LATEST_SCHEMA_VERSION, get_user_version

            version = get_user_version(conn)
            if version == LATEST_SCHEMA_VERSION:
                return {
                    "name": "Database",
                    "status": "pass",
                    "detail": f"schema v{version} at {db_path}",
                }
            if version < LATEST_SCHEMA_VERSION:
                return {
                    "name": "Database",
                    "status": "warn",
                    "detail": (
                        f"schema v{version} (latest is v{LATEST_SCHEMA_VERSION}) — "
                        f"will auto-migrate on next start: {db_path}"
                    ),
                }
            return {
                "name": "Database",
                "status": "fail",
                "detail": (
                    f"schema v{version} is newer than this build supports "
                    f"(v{LATEST_SCHEMA_VERSION}). Upgrade atlasbridge or delete {db_path}"
                ),
            }
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return {"name": "Database", "status": "fail", "detail": str(exc)}


def _check_adapters() -> dict:
    """Check that at least one adapter is registered."""
    try:
        import atlasbridge.adapters  # noqa: F401
        from atlasbridge.adapters.base import AdapterRegistry

        adapters = AdapterRegistry.list_all()
        if not adapters:
            return {
                "name": "Adapters",
                "status": "fail",
                "detail": "no adapters registered — reinstall: pip install -U atlasbridge",
            }
        names = ", ".join(sorted(adapters.keys()))
        return {
            "name": "Adapters",
            "status": "pass",
            "detail": names,
        }
    except Exception as exc:  # noqa: BLE001
        return {"name": "Adapters", "status": "fail", "detail": str(exc)}


def cmd_doctor(fix: bool, as_json: bool, console: Console) -> None:
    if fix:
        _fix_config(console)
        _fix_database(console)
        _fix_stale_pid(console)
        _fix_permissions(console)

    checks_raw: list[dict | None] = [
        _check_python_version(),
        _check_platform(),
        _check_ptyprocess(),
        _check_config(),
        _check_bot_token(),
        _check_telegram_reachability(),
        _check_database(),
        _check_adapters(),
        _check_ui_assets(),
        _check_stale_pid(),
        _check_permissions(),
        _check_poller_lock(),
        _check_systemd(),
        _check_systemd_service(),
    ]
    checks: list[dict] = [c for c in checks_raw if c is not None]

    all_pass = all(c["status"] in ("pass", "skip") for c in checks)

    if as_json:
        print(json.dumps({"checks": checks, "all_pass": all_pass}, indent=2))
        return

    console.print("[bold]AtlasBridge Doctor[/bold]\n")
    for c in checks:
        if c["status"] == "pass":
            icon = "[green]PASS[/green]"
        elif c["status"] == "skip":
            icon = "[dim]SKIP[/dim]"
        elif c["status"] == "warn":
            icon = "[yellow]WARN[/yellow]"
        else:
            icon = "[red]FAIL[/red]"
        console.print(f"  {icon}  {c['name']}: {c['detail']}")

    console.print()
    if all_pass:
        console.print("[green]All checks passed.[/green]")
    else:
        fails = [c for c in checks if c["status"] == "fail"]
        warns = [c for c in checks if c["status"] == "warn"]
        if fails:
            console.print("[red]Some checks failed.[/red]")
            if not fix:
                console.print("Run [cyan]atlasbridge doctor --fix[/cyan] to auto-repair.")
        elif warns:
            console.print("[yellow]Some checks have warnings. Review above for details.[/yellow]")

    if not all_pass:
        console.print("\nNext steps:")
        console.print("  1. [cyan]atlasbridge setup[/cyan] — configure Telegram or Slack")
        console.print("  2. [cyan]atlasbridge doctor --fix[/cyan] — auto-repair config issues")
        console.print("  3. [cyan]atlasbridge run claude[/cyan] — start supervising")
