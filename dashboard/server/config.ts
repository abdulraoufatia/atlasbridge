import os from "os";
import path from "path";
import fs from "fs";

export function getAtlasBridgeDir(): string {
  // Check env vars first
  if (process.env.ATLASBRIDGE_CONFIG) return process.env.ATLASBRIDGE_CONFIG;
  if (process.env.AEGIS_CONFIG) return process.env.AEGIS_CONFIG;

  // Platform-specific defaults
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library", "Application Support", "atlasbridge");
  }
  if (process.env.XDG_CONFIG_HOME) {
    return path.join(process.env.XDG_CONFIG_HOME, "atlasbridge");
  }
  return path.join(os.homedir(), ".config", "atlasbridge");
}

export function getAtlasBridgeDbPath(): string {
  if (process.env.ATLASBRIDGE_DB_PATH) return process.env.ATLASBRIDGE_DB_PATH;
  return path.join(getAtlasBridgeDir(), "atlasbridge.db");
}

export function getDashboardDbPath(): string {
  if (process.env.DASHBOARD_DB_PATH) return process.env.DASHBOARD_DB_PATH;
  return path.join(getAtlasBridgeDir(), "dashboard.db");
}

export function getTracePath(): string {
  if (process.env.ATLASBRIDGE_TRACE_PATH) return process.env.ATLASBRIDGE_TRACE_PATH;
  return path.join(getAtlasBridgeDir(), "autopilot_decisions.jsonl");
}

export function getConfigPath(): string {
  return path.join(getAtlasBridgeDir(), "config.yaml");
}

export function ensureDir(dirPath: string): void {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}
