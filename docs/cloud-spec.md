# Cloud Module Specification (Phase B)

> **Maturity:** Specification only — no HTTP implementation exists.
> **Status:** Extracted from `src/atlasbridge/cloud/` (7 source files, 415 lines) in v0.8.2 to reduce maintenance surface. Interfaces will be restored to source when Phase B implementation begins.

This document preserves the complete interface definitions for the cloud governance integration layer. The local runtime functions identically without these interfaces — cloud is always opt-in and disabled by default.

---

## Design Principles

1. **Cloud OBSERVES, does not EXECUTE** — no execution commands flow from cloud to runtime
2. **Local runtime is source of truth** — cloud streaming is fire-and-forget
3. **Graceful degradation** — all interfaces have no-op disabled implementations
4. **Network isolation** — no HTTP libraries (httpx, requests, aiohttp, urllib3) in cloud module
5. **Security by default** — keypair stays local, only public key goes to cloud

---

## CloudConfig

```python
from dataclasses import dataclass

@dataclass
class CloudConfig:
    """Cloud integration configuration.

    All fields default to disabled/empty. The runtime must function
    identically when cloud is disabled — this is a non-negotiable invariant.
    """
    enabled: bool = False
    endpoint: str = ""
    org_id: str = ""
    api_token: str = ""  # Will be stored in keyring in production
    control_channel: str = "disabled"  # disabled | local_only | hybrid
    stream_audit: bool = False


def is_cloud_enabled(config: CloudConfig | None = None) -> bool:
    """Check if cloud features are active.
    Returns False if config is None or cloud is not enabled.
    """
    if config is None:
        return False
    return config.enabled and bool(config.endpoint)
```

---

## Authentication (`auth.py`)

The local runtime authenticates to the cloud API using a local Ed25519 keypair. The public key serves as the runtime identity. No secrets are ever exported to the cloud.

**Contract:**
- Keypair is generated locally on first cloud setup
- Private key never leaves the local machine
- Runtime identity = hex-encoded public key
- API tokens are stored in the OS keyring (not config files)

```python
from abc import ABC, abstractmethod

class CloudAuthProvider(ABC):
    """Interface for cloud authentication."""

    @abstractmethod
    def get_runtime_id(self) -> str:
        """Return the runtime identity (public key hex)."""

    @abstractmethod
    def sign(self, message: bytes) -> bytes:
        """Sign a message with the local private key."""

    @abstractmethod
    def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool:
        """Verify a signature against a public key."""

    @abstractmethod
    def get_api_token(self) -> str:
        """Retrieve the API token from the keyring."""


class DisabledAuthProvider(CloudAuthProvider):
    """No-op auth provider used when cloud is disabled."""

    def get_runtime_id(self) -> str: return ""
    def sign(self, message: bytes) -> bytes: return b""
    def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool: return False
    def get_api_token(self) -> str: return ""
```

---

## Transport (`transport.py`)

WebSocket-based (WSS) secure control channel transport with automatic reconnection and exponential backoff.

**Contract:**
- Transport failure degrades gracefully (local runtime continues)
- Reconnection is automatic with bounded backoff
- No execution commands flow from cloud to runtime
- Cloud-to-runtime messages are advisory only (policy update hints, kill switch signals that the runtime MAY honor)

```python
from abc import ABC, abstractmethod
from typing import Any

class ControlChannelTransport(ABC):
    """Interface for the secure control channel transport."""

    @abstractmethod
    async def connect(self, endpoint: str, runtime_id: str) -> bool:
        """Establish a connection. Returns True if connected."""

    @abstractmethod
    async def send(self, message: dict[str, Any]) -> bool:
        """Send a signed message. Returns True if sent."""

    @abstractmethod
    async def receive(self) -> dict[str, Any] | None:
        """Receive the next advisory message. Returns None if disconnected."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the cloud control channel."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the transport is currently connected."""


class DisabledTransport(ControlChannelTransport):
    """No-op transport used when cloud is disabled."""

    async def connect(self, endpoint: str, runtime_id: str) -> bool: return False
    async def send(self, message: dict[str, Any]) -> bool: return False
    async def receive(self) -> dict[str, Any] | None: return None
    async def disconnect(self) -> None: pass
    def is_connected(self) -> bool: return False
```

---

## Client Interfaces (`client.py`)

### PolicyRegistryClient

Cloud-hosted policy registry storing signed policy snapshots.

**Contract:**
- Pull is always optional (local policy file takes precedence)
- Signatures use Ed25519 (runtime holds the public key)
- Pull failure never blocks local policy evaluation

```python
from abc import ABC, abstractmethod
from typing import Any

class PolicyRegistryClient(ABC):

    @abstractmethod
    async def pull_policy(self, org_id: str, policy_name: str) -> dict[str, Any] | None:
        """Pull the latest signed policy snapshot. Returns None if unavailable."""

    @abstractmethod
    async def push_policy(self, org_id: str, policy_name: str, policy_yaml: str) -> bool:
        """Push a local policy. Returns True on success."""

    @abstractmethod
    async def verify_signature(self, policy_data: dict[str, Any]) -> bool:
        """Verify the Ed25519 signature of a policy snapshot."""


class DisabledPolicyRegistry(PolicyRegistryClient):
    """No-op policy registry used when cloud is disabled."""

    async def pull_policy(self, org_id: str, policy_name: str) -> dict[str, Any] | None: return None
    async def push_policy(self, org_id: str, policy_name: str, policy_yaml: str) -> bool: return False
    async def verify_signature(self, policy_data: dict[str, Any]) -> bool: return False
```

### EscalationRelayClient

Routes escalation events through the cloud governance API to additional channels (email, PagerDuty, etc.) beyond the local Telegram/Slack channels.

**Contract:**
- Relay failure never blocks local escalation
- Local channels always fire first
- Cloud relay is fire-and-forget with retry

```python
class EscalationRelayClient(ABC):

    @abstractmethod
    async def relay_escalation(
        self, session_id: str, prompt_id: str, escalation_data: dict[str, Any],
    ) -> bool:
        """Relay an escalation event. Returns True if accepted (not necessarily delivered)."""
```

---

## Protocol (`protocol.py`)

Control channel message types and framing for the secure control channel.

**Protocol principles:**
- Cloud OBSERVES, does not EXECUTE
- All messages are signed by the runtime's local keypair
- Replay protection via monotonic sequence numbers
- Idempotent message processing (server deduplicates by message_id)

```python
from dataclasses import dataclass, field
from enum import StrEnum

class MessageType(StrEnum):
    """Control channel message types."""

    # Runtime -> Cloud
    HEARTBEAT = "heartbeat"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    DECISION_MADE = "decision_made"
    ESCALATION_TRIGGERED = "escalation_triggered"
    POLICY_LOADED = "policy_loaded"

    # Cloud -> Runtime (advisory only — runtime may ignore)
    POLICY_UPDATE_AVAILABLE = "policy_update_available"
    KILL_SWITCH = "kill_switch"


@dataclass
class ControlMessage:
    """A single control channel message.

    All messages carry a signature from the runtime's local keypair.
    The cloud API verifies signatures but NEVER sends execution commands.
    """
    message_id: str          # Unique, monotonic
    message_type: MessageType
    timestamp: str           # ISO8601
    org_id: str
    runtime_id: str          # Derived from local keypair public key
    sequence: int            # Monotonic sequence number for replay protection
    payload: dict[str, object] = field(default_factory=dict)
    signature: str = ""      # Ed25519 signature of (message_id + type + timestamp + payload)


@dataclass
class ProtocolSpec:
    """Protocol specification constants."""
    version: str = "1.0"
    transport: str = "wss"              # WebSocket Secure
    encoding: str = "json"
    max_message_size_bytes: int = 65536 # 64 KB
    heartbeat_interval_seconds: int = 30
    reconnect_backoff_base_seconds: float = 1.0
    reconnect_backoff_max_seconds: float = 300.0
    signature_algorithm: str = "Ed25519"
    dedup_window_seconds: int = 3600    # 1 hour
```

---

## Audit Stream (`audit_stream.py`)

Sends COPIES of local decision trace entries to the cloud governance API for centralized observability. The local trace file is always the source of truth.

**Contract:**
- Stream failure never affects local trace writing
- Entries are buffered locally and sent in batches
- Duplicate delivery is safe (server deduplicates by idempotency_key)
- No sensitive data (prompt content, reply values) is streamed — only metadata

```python
from abc import ABC, abstractmethod
from typing import Any

class AuditStreamClient(ABC):
    """Interface for streaming audit events to the cloud."""

    @abstractmethod
    async def stream_entry(self, entry: dict[str, Any]) -> bool:
        """Stream a single trace entry. Returns True if accepted."""

    @abstractmethod
    async def flush(self) -> int:
        """Flush buffered entries. Returns count of entries sent."""

    @abstractmethod
    async def close(self) -> None:
        """Close the stream connection."""


class DisabledAuditStream(AuditStreamClient):
    """No-op audit stream used when cloud is disabled."""

    async def stream_entry(self, entry: dict[str, Any]) -> bool: return False
    async def flush(self) -> int: return 0
    async def close(self) -> None: pass
```

---

## Implementation Notes

When Phase B implementation begins, restore these interfaces to source code at `src/atlasbridge/cloud/` and implement:

1. `auth.py` — Ed25519 keypair generation, OS keyring integration
2. `transport.py` — WebSocket client with exponential backoff reconnection
3. `client.py` — HTTP client for policy registry and escalation relay
4. `audit_stream.py` — Batched, buffered audit event streaming
5. `protocol.py` — Wire protocol framing and signature verification

Dependencies to add: `cryptography` (Ed25519), `websockets` (transport)

Network isolation test (guard): ensure no HTTP library imports leak into the cloud module at import time.
