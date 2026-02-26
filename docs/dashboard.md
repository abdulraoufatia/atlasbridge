# Dashboard — Deployment & Usage Guide

AtlasBridge ships a **local, read-only governance dashboard** for viewing sessions, prompts, decision traces, and audit integrity. It runs on your machine and connects to the local SQLite database — no external dependencies.

> **The dashboard has NO built-in authentication.** Do not expose it to the public internet without adding your own auth layer.

---

## Quick Start

```bash
# Install dashboard dependencies (if not already)
pip install 'atlasbridge[dashboard]'

# Start the dashboard (opens browser automatically)
atlasbridge dashboard start

# Start without opening the browser
atlasbridge dashboard start --no-browser

# Check if the dashboard is running
atlasbridge dashboard status

# Custom port
atlasbridge dashboard start --port 9090
```

The dashboard binds to `127.0.0.1:8787` by default — only accessible from your local machine.

---

## Remote Access via SSH Tunnel (Recommended)

The safest way to access the dashboard from another device (phone, tablet, laptop) is an SSH tunnel. No firewall changes, no exposure.

### From a remote machine

```bash
# On the remote machine (your laptop, phone via Termux, etc.):
ssh -L 8787:localhost:8787 user@your-server

# Then open http://localhost:8787 in your browser
```

### Persistent tunnel

```bash
# Background tunnel that reconnects automatically:
ssh -f -N -L 8787:localhost:8787 user@your-server
```

### From an iPad / mobile

Use an SSH client app (e.g., Termius, Blink Shell) to set up a local port forward:

- **Local port:** 8787
- **Remote host:** localhost
- **Remote port:** 8787

Then open `http://localhost:8787` in the mobile browser.

---

## Reverse Proxy (Advanced)

If you need the dashboard accessible on your local network (e.g., from a phone on the same Wi-Fi), you can use a reverse proxy with authentication.

### **DO NOT EXPOSE WITHOUT AUTH**

The dashboard shows session data, prompt excerpts, and decision traces. While tokens are redacted, exposing it without authentication leaks operational details.

### Nginx Example

```nginx
server {
    listen 443 ssl;
    server_name dashboard.internal;

    ssl_certificate     /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # Basic authentication
    auth_basic "AtlasBridge Dashboard";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8787;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Create the password file:

```bash
# Install htpasswd (usually in apache2-utils)
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

### Caddy Example

```
dashboard.internal {
    basicauth {
        admin $2a$14$... # bcrypt hash from `caddy hash-password`
    }
    reverse_proxy 127.0.0.1:8787
}
```

Generate a password hash:

```bash
caddy hash-password
```

### Binding to Non-Loopback Addresses

By default, AtlasBridge refuses to bind to non-loopback addresses. If your reverse proxy runs on the same machine, you don't need to change this — proxy to `127.0.0.1:8787`.

If you must bind to all interfaces (e.g., Docker networking):

```bash
atlasbridge dashboard start --host 0.0.0.0 --i-understand-risk
```

The `--i-understand-risk` flag is intentionally verbose. It is hidden from `--help` to prevent accidental use.

---

## Session Export

Export session data for offline review, sharing, or archival.

### CLI Export

```bash
# Export as JSON (written to stdout)
atlasbridge dashboard export --session sess-001

# Export as JSON to a file
atlasbridge dashboard export --session sess-001 --output report.json

# Export as self-contained HTML
atlasbridge dashboard export --session sess-001 --format html

# Export HTML to a specific file
atlasbridge dashboard export --session sess-001 --format html --output report.html
```

### API Export

While the dashboard is running, you can also fetch the export via HTTP:

```bash
curl http://localhost:8787/api/sessions/sess-001/export | python3 -m json.tool
```

### What's Included

Each export contains:

- **Session metadata** — ID, tool, status, timestamps, working directory
- **Prompts** — all prompts detected during the session
- **Decision traces** — autopilot decisions for the session
- **Audit events** — hash-chained audit entries for the session

All text fields are sanitized: ANSI codes stripped, tokens redacted, content truncated to safe lengths.

---

## Mobile Access

The dashboard is responsive and works on phones and tablets:

- **Tables** scroll horizontally on narrow screens
- **Navigation** collapses to a hamburger menu on mobile
- **Touch targets** are at least 44px for comfortable tapping
- **Filter bars** stack vertically on small screens
- **Stat cards** reflow to 2-column or single-column layouts

For mobile access, use an SSH tunnel (see above) — this keeps the dashboard secure without exposing it to the network.

---

## Security Considerations

| Property | Status |
|----------|--------|
| Authentication | **None** — add your own via proxy |
| Database access | Read-only (`mode=ro` SQLite) |
| Token redaction | Automatic — `sk-`, `xoxb-`, `ghp_`, AWS keys redacted |
| ANSI stripping | Automatic — all escape codes removed |
| Mutation routes | None — no PUT, DELETE, PATCH endpoints |
| Default binding | `127.0.0.1` (loopback only) |
| Non-loopback binding | Requires `--i-understand-risk` flag |

---

## Troubleshooting

### Port already in use

```bash
# Check what's using port 8787
lsof -i :8787

# Use a different port
atlasbridge dashboard start --port 9090
```

### Missing dependencies

```bash
pip install 'atlasbridge[dashboard]'
# or with uv:
uv pip install 'atlasbridge[dashboard]'
```

### No data showing

The dashboard reads from the AtlasBridge SQLite database. If no sessions have been run yet, the dashboard shows an empty state. Run a session first:

```bash
atlasbridge run claude
```

### SSH tunnel not working

Verify the dashboard is running on the remote machine:

```bash
ssh user@your-server "curl -s http://localhost:8787/api/stats"
```

If that returns JSON, the dashboard is running. Check your SSH tunnel configuration.
