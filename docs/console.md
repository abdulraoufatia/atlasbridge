# Operator Console

The operator console (`atlasbridge console`) is a single-command Textual TUI that manages daemon, agent, and dashboard processes from one screen, with live status polling, inline diagnostics, and audit log tailing.

## Quick Start

```bash
atlasbridge console
```

Options:
```bash
atlasbridge console --tool openai          # Default agent tool
atlasbridge console --dashboard-port 9000  # Custom dashboard port
```

## Layout

```
┌─ Header: "AtlasBridge Console v0.9.x" ──────────────────────┐
│                                                              │
│ OPERATOR CONSOLE — LOCAL EXECUTION ONLY                      │
│                                                              │
│ ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────────┐       │
│ │ Daemon  │ │Dashboard│ │ Agent    │ │ Channel     │       │
│ │ Running │ │ Stopped │ │ Running  │ │ telegram    │       │
│ └─────────┘ └─────────┘ └──────────┘ └─────────────┘       │
│                                                              │
│ ┌─ Managed Processes ─────────────────────────────────────┐  │
│ │ TYPE        PID     STATUS     UPTIME     INFO          │  │
│ │ daemon      1234    running    5m 32s                    │  │
│ │ dashboard   1235    running    5m 10s     port 8787     │  │
│ │ agent       1236    running    4m 58s     claude        │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ Doctor ────────────────────────────────────────────────┐  │
│ │ OK Python  OK Config  OK Token  OK Database             │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ Audit Log (recent) ───────────────────────────────────┐  │
│ │ 10:30 prompt_detected      session abc123               │  │
│ │ 10:31 prompt_forwarded     telegram -> user 12345       │  │
│ └─────────────────────────────────────────────────────────┘  │
│                                                              │
│ [D]aemon [A]gent [W]eb [H]ealth [R]efresh [Q]uit           │
└──────────────────────────────────────────────────────────────┘
```

## Keybindings

| Key | Action | Behavior |
|-----|--------|----------|
| `d` | Toggle daemon | Start if stopped, stop if running |
| `a` | Toggle agent | Start with default tool if stopped, stop if running |
| `w` | Toggle dashboard | Start if stopped, stop if running |
| `h` | Run doctor | Refresh the doctor panel with health checks |
| `r` | Refresh all | Force poll all status and reload audit log |
| `q` | Quit | Stop all managed processes and exit |
| `Esc` | Quit | Same as `q` |

## Process Management

The console manages three process types by spawning AtlasBridge CLI subcommands as subprocesses:

### Daemon

- **Start**: Runs `atlasbridge start` which forks to background and writes a PID file.
- **Stop**: Reads PID from file, sends SIGTERM, falls back to SIGKILL.
- **Status**: Reads PID file + `os.kill(pid, 0)` liveness check.

### Dashboard

- **Start**: Runs `atlasbridge dashboard start --no-browser --port <port>` as a long-running subprocess.
- **Stop**: Sends SIGTERM to the subprocess.
- **Status**: TCP socket probe on the configured port.

### Agent

- **Start**: Runs `atlasbridge run <tool>` as a long-running subprocess.
- **Stop**: Sends SIGTERM to the subprocess.
- **Status**: Tracks subprocess PID and return code.

## Status Polling

The console polls all process statuses every 2 seconds using `set_interval()`. Each poll cycle:

1. Checks daemon PID (via PID file)
2. Checks dashboard port (TCP socket connect)
3. Checks agent subprocess (return code)
4. Reads channel configuration status
5. Updates all UI panels reactively

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--tool` | `claude` | Default agent tool to launch with `a` key |
| `--dashboard-port` | `8787` | Port for the dashboard server |

## Safety

The console displays a permanent safety banner:

> OPERATOR CONSOLE — LOCAL EXECUTION ONLY

This is a reminder that:
- All processes run locally on the operator's machine
- The dashboard has no authentication (localhost only by default)
- No cloud execution or remote management is involved

## Relationship to `atlasbridge ui`

| Feature | `atlasbridge ui` | `atlasbridge console` |
|---------|-------------------|-----------------------|
| Purpose | Setup and status viewer | Operations controller |
| Manages processes | No | Yes (daemon, dashboard, agent) |
| Setup wizard | Yes | No |
| Doctor checks | Full screen | Inline panel |
| Audit log | Full screen | Inline panel |
| Keybindings | Navigation (S/L/D/Q) | Process control (D/A/W/H/R/Q) |
| Shutdown behavior | Simple exit | Stops managed processes |

Use `atlasbridge ui` for initial setup and configuration. Use `atlasbridge console` for day-to-day operations.

## Troubleshooting

### Console says "Stopped" but process is running

The console only tracks processes it started. If you started the daemon in another terminal, the console detects it via the PID file but marks it as externally managed.

### Dashboard won't start

Check if the port is already in use:
```bash
atlasbridge dashboard status --port 8787
```

### Agent won't start

Ensure the tool is installed and on PATH:
```bash
atlasbridge adapters
```

### TTY required error

The console requires an interactive terminal:
```bash
# Won't work
echo | atlasbridge console

# Works
atlasbridge console
```
