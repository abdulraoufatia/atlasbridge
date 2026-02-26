# Upgrading AtlasBridge

## Checking for Updates

AtlasBridge automatically checks for new versions and notifies you across all interfaces:

- **CLI** — run `atlasbridge version` to see if an update is available
- **Dashboard** — an amber banner appears at the top of the page when a newer version exists
- **Console** — the status line shows an update notice

Version checks are cached locally for 24 hours and never block normal operation. No data is sent to PyPI beyond a standard package metadata request.

## Quick Upgrade

```bash
pip install -U atlasbridge
```

Your configuration, tokens, and database are preserved. They live in a platform-specific directory that `pip install` does not touch.

## What Gets Preserved

| Item | Location | Preserved? |
|------|----------|-----------|
| Config file | `config.toml` | Yes |
| Bot tokens | config.toml or OS keyring | Yes |
| Database | `atlasbridge.db` | Yes |
| Audit log | `audit.log` | Yes |
| Decision trace | `autopilot_decisions.jsonl` | Yes |
| Policy files | user-specified path | Yes |

## Config Locations

| Platform | Directory |
|----------|-----------|
| macOS | `~/Library/Application Support/atlasbridge/` |
| Linux | `~/.config/atlasbridge/` (or `$XDG_CONFIG_HOME/atlasbridge/`) |
| Override | Set `ATLASBRIDGE_CONFIG` env var |

## Verify After Upgrade

```bash
atlasbridge version        # confirm new version
atlasbridge doctor         # verify all checks pass
atlasbridge adapter list   # verify adapters loaded
```

## Setup on Upgrade

If you run `atlasbridge setup` after an upgrade, it will detect your existing config:

```
Existing config found: /path/to/config.toml
Keep existing configuration? [Y/n]
```

Choose **Y** to keep everything as-is. Choose **N** only if you want to reconfigure from scratch.

## Migrating from Aegis

If you previously used the `aegis` name (pre-v0.4.0), AtlasBridge auto-migrates from `~/.aegis/` on first run. This happens once — a `.migrated_from_aegis` marker file prevents repeated migration.

## Config Version Upgrades

AtlasBridge auto-upgrades config file format when needed. The `config_version` field in `config.toml` tracks the schema version. Upgrades are applied in-place and the file is rewritten with secure permissions.
