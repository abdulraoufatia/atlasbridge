# Audit Export

**Version:** 1.6.x
**Status:** Stable

AtlasBridge maintains an append-only, hash-chained audit log. This document specifies the export format, integrity verification, and integration patterns.

---

## Overview

The audit log records every governance decision — prompt detected, routed, replied to, injected, expired, or rejected. Each entry is linked to the previous via SHA-256 hash chain. Truncation and tampering are detectable.

---

## Export via CLI

```bash
# Export last 100 audit events as JSON
atlasbridge audit export --format json --limit 100 > audit-2026.json

# Export all events since a date
atlasbridge audit export --format json --since 2026-01-01

# Verify integrity before export
atlasbridge audit verify

# Export with integrity hash embedded
atlasbridge audit export --format json --verify > audit-2026.json
```

---

## JSON export format

Each export is a JSON object with a metadata header and an events array.

```json
{
  "export_version": "1",
  "exported_at": "2026-02-26T20:00:00Z",
  "chain_head_hash": "a1b2c3...64hex",
  "chain_verified": true,
  "event_count": 142,
  "events": [
    {
      "id": "3f8a1b2c4d5e",
      "event_type": "session_started",
      "session_id": "sess-001",
      "prompt_id": "",
      "payload": { "tool": "claude", "command": ["claude"] },
      "timestamp": "2026-02-26T19:00:00.123456+00:00",
      "prev_hash": "",
      "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  ]
}
```

### Field reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique event identifier (random hex, 24 chars) |
| `event_type` | string | One of the event types listed below |
| `session_id` | string | Session that produced this event |
| `prompt_id` | string | Associated prompt (empty for session-level events) |
| `payload` | object | Event-specific fields (see event types) |
| `timestamp` | string | ISO 8601 UTC timestamp |
| `prev_hash` | string | SHA-256 of previous event (empty for first event) |
| `hash` | string | SHA-256 of this event (see algorithm below) |

---

## Hash chain algorithm

```
chain_input = prev_hash + event_id + event_type + json(payload, sorted_keys=True)
hash        = SHA-256(chain_input.encode("utf-8")).hexdigest()
```

The first event in the chain has `prev_hash = ""`.

### Verification

```python
import hashlib, json

def verify_chain(events: list[dict]) -> bool:
    expected_prev = ""
    for event in events:
        chain_input = (
            event["prev_hash"]
            + event["id"]
            + event["event_type"]
            + json.dumps(event["payload"], separators=(",", ":"), sort_keys=True)
        )
        expected_hash = hashlib.sha256(chain_input.encode()).hexdigest()
        if event["hash"] != expected_hash:
            return False
        if event["prev_hash"] != expected_prev:
            return False
        expected_prev = event["hash"]
    return True
```

---

## Event types

| Event type | Description |
|-----------|-------------|
| `session_started` | New CLI session opened |
| `session_ended` | CLI session terminated |
| `prompt_detected` | PromptDetector fired (signal 1/2/3) |
| `prompt_routed` | Sent to escalation channel |
| `reply_received` | Human reply received from channel |
| `response_injected` | Reply bytes written to PTY stdin |
| `prompt_expired` | TTL elapsed; safe default applied |
| `duplicate_callback_ignored` | Nonce replay rejected |
| `late_reply_rejected` | Reply arrived after TTL |
| `invalid_callback` | Unknown or mismatched prompt_id |
| `channel_message_accepted` | Gate accepted incoming channel message |
| `channel_message_rejected` | Gate rejected incoming channel message |
| `capability.denied` | Capability access denied |
| `daemon_restarted` | Daemon process restarted |
| `telegram_polling_failed` | Telegram API unreachable |

---

## Integrity verification

```bash
# Verify hash chain integrity
atlasbridge audit verify

# Output (clean):
# ✓ Chain verified: 142 events, head=a1b2c3...
# ✓ No gaps detected
# ✓ No tampering detected

# Output (tampered):
# ✗ Chain broken at event 47: hash mismatch
# ✗ Chain broken at event 48: prev_hash mismatch
```

The audit verify command re-computes the hash of every event in the chain and checks linkage. Any modification to a stored event is detectable.

---

## Append-only guarantees

1. The audit log is written with `O_APPEND` semantics at the file level.
2. Each event is committed with `db.commit()` immediately after write.
3. SQLite WAL mode prevents partial writes from corrupting existing events.
4. Hash chain linkage detects any deletion, reordering, or modification.

**What the hash chain detects:**
- Payload tampering (any field change)
- Event type forgery
- Row deletion (gap in prev_hash linkage)
- Phantom insertion (fabricated hash doesn't match computed value)
- Row reordering (prev_hash linkage breaks)

**What the hash chain does not detect:**
- Deletion of the entire log (the log is gone)
- Replacement of the entire log with a forged chain

For environments requiring stronger guarantees, ship audit events to an external immutable store (syslog, SIEM, or S3 with object lock).

---

## Export verification workflow

```bash
# Step 1: Verify chain integrity
atlasbridge audit verify

# Step 2: Export
atlasbridge audit export --format json --verify > audit-bundle.json

# Step 3: Verify the exported bundle independently
python3 -c "
import json, hashlib
bundle = json.load(open('audit-bundle.json'))
events = bundle['events']
prev = ''
for e in events:
    inp = e['prev_hash'] + e['id'] + e['event_type'] + json.dumps(e['payload'], separators=(',',':'), sort_keys=True)
    h = hashlib.sha256(inp.encode()).hexdigest()
    assert h == e['hash'], f'Hash mismatch at {e[\"id\"]}'
    assert e['prev_hash'] == prev, f'Chain break at {e[\"id\"]}'
    prev = h
print(f'✓ {len(events)} events verified')
"
```

---

## Integration patterns

### SIEM forwarding

```bash
# Forward new audit events to syslog (run as cron or systemd timer)
atlasbridge audit export --format jsonl --since "$(date -d '1 hour ago' --iso-8601=seconds)" \
  | logger -t atlasbridge -p local0.info
```

### S3 with object lock

```bash
atlasbridge audit export --format json --verify | \
  aws s3 cp - s3://my-bucket/atlasbridge/audit-$(date +%Y%m%d).json \
    --no-progress
```

### Grafana / dashboard

The dashboard's `/api/audit` endpoint returns the most recent 1000 audit events as JSON, paginated. Suitable for Grafana JSON datasource.
