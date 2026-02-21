"""aegis doctor — environment and configuration health check."""

from __future__ import annotations

import json
import shutil
import sys

from rich.console import Console


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
    return {
        "name": "Platform",
        "status": "pass" if supported else "warn",
        "detail": plat + ("" if supported else " (Windows is experimental)"),
    }


def _check_ptyprocess() -> dict:
    try:
        import ptyprocess  # type: ignore[import]  # noqa: F401

        return {"name": "ptyprocess", "status": "pass", "detail": "installed"}
    except ImportError:
        return {
            "name": "ptyprocess",
            "status": "fail",
            "detail": "not installed — run: pip install ptyprocess",
        }


def _check_config() -> dict:
    try:
        from atlasbridge.core.config import atlasbridge_dir, load_config

        cfg_path = atlasbridge_dir() / "config.toml"
        if not cfg_path.exists():
            return {
                "name": "Config file",
                "status": "warn",
                "detail": f"not found at {cfg_path} — run: atlasbridge setup",
            }
        load_config(str(cfg_path))
        return {"name": "Config file", "status": "pass", "detail": str(cfg_path)}
    except Exception as exc:  # noqa: BLE001
        return {"name": "Config file", "status": "fail", "detail": str(exc)}


def _check_bot_token() -> dict:
    try:
        from atlasbridge.core.config import atlasbridge_dir, load_config

        cfg_path = atlasbridge_dir() / "config.toml"
        if not cfg_path.exists():
            return {"name": "Bot token", "status": "skip", "detail": "no config file"}
        cfg = load_config(str(cfg_path))
        token = cfg.telegram.bot_token if cfg.telegram else ""
        if not token:
            return {
                "name": "Bot token",
                "status": "warn",
                "detail": "not configured — run: atlasbridge setup",
            }
        masked = token[:8] + "..." + token[-4:]
        return {"name": "Bot token", "status": "pass", "detail": masked}
    except Exception as exc:  # noqa: BLE001
        return {"name": "Bot token", "status": "fail", "detail": str(exc)}


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


def _check_systemd_service() -> dict | None:
    """Linux-only: check if the aegis.service unit is installed."""
    if not sys.platform.startswith("linux"):
        return None
    from atlasbridge.os.systemd.service import systemd_user_dir

    unit_path = systemd_user_dir() / "aegis.service"
    if unit_path.exists():
        return {"name": "aegis.service", "status": "pass", "detail": str(unit_path)}
    return {
        "name": "aegis.service",
        "status": "warn",
        "detail": "not installed — run: atlasbridge setup --install-service",
    }


def cmd_doctor(fix: bool, as_json: bool, console: Console) -> None:
    checks_raw: list[dict | None] = [
        _check_python_version(),
        _check_platform(),
        _check_ptyprocess(),
        _check_config(),
        _check_bot_token(),
        _check_ui_assets(),
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
            console.print("[red]Some checks failed. Run with --fix to auto-repair.[/red]")
        elif warns:
            console.print("[yellow]Some checks have warnings. Review above for details.[/yellow]")
