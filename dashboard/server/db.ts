import Database from "better-sqlite3";
import { drizzle } from "drizzle-orm/better-sqlite3";
import * as schema from "@shared/schema";
import { getAtlasBridgeDbPath, getDashboardDbPath } from "./config";

// Dashboard settings DB (read-write) — stores RBAC, settings, etc.
const dashboardDbPath = getDashboardDbPath();
const dashboardSqlite = new Database(dashboardDbPath);
dashboardSqlite.pragma("journal_mode = WAL");
dashboardSqlite.pragma("foreign_keys = ON");

// Create tables if they don't exist
dashboardSqlite.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Viewer',
    status TEXT NOT NULL DEFAULT 'pending',
    mfa_status TEXT NOT NULL DEFAULT 'disabled',
    last_active TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    groups TEXT NOT NULL DEFAULT '[]',
    login_method TEXT NOT NULL DEFAULT 'SSO'
  );
  CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    member_count INTEGER NOT NULL DEFAULT 0,
    roles TEXT NOT NULL DEFAULT '[]',
    permission_level TEXT NOT NULL DEFAULT 'read',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    sync_source TEXT NOT NULL DEFAULT 'Manual',
    last_synced TEXT
  );
  CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    permissions TEXT NOT NULL DEFAULT '[]',
    is_system INTEGER NOT NULL DEFAULT 0,
    member_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );
  CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    prefix TEXT NOT NULL,
    scopes TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,
    last_used TEXT,
    rate_limit INTEGER NOT NULL DEFAULT 100
  );
  CREATE TABLE IF NOT EXISTS security_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    value TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info'
  );
  CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    channel TEXT NOT NULL,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    destination TEXT NOT NULL,
    events TEXT NOT NULL DEFAULT '[]',
    min_severity TEXT NOT NULL DEFAULT 'info',
    last_delivered TEXT
  );
  CREATE TABLE IF NOT EXISTS ip_allowlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT NOT NULL UNIQUE,
    cidr TEXT NOT NULL,
    label TEXT NOT NULL,
    added_by TEXT NOT NULL,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_hit TEXT
  );
  CREATE TABLE IF NOT EXISTS repo_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT 'main',
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'connected',
    access_token TEXT,
    connected_by TEXT NOT NULL,
    connected_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_synced TEXT,
    compliance_level TEXT NOT NULL DEFAULT 'standard',
    compliance_score INTEGER
  );
  CREATE TABLE IF NOT EXISTS compliance_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_connection_id INTEGER NOT NULL,
    scan_date TEXT NOT NULL DEFAULT (datetime('now')),
    compliance_level TEXT NOT NULL,
    overall_score INTEGER NOT NULL,
    categories TEXT NOT NULL,
    suggestions TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS operator_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    action TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '{}',
    result TEXT NOT NULL DEFAULT 'ok',
    error TEXT
  );
`);

export const db = drizzle(dashboardSqlite, { schema });

export function insertOperatorAuditLog(entry: {
  method: string;
  path: string;
  action: string;
  body: Record<string, unknown>;
  result: "ok" | "error";
  error?: string;
}): void {
  dashboardSqlite
    .prepare(
      `INSERT INTO operator_audit_log (method, path, action, body, result, error)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .run(
      entry.method,
      entry.path,
      entry.action,
      JSON.stringify(entry.body),
      entry.result,
      entry.error ?? null,
    );
}

export function queryOperatorAuditLog(limit = 100): unknown[] {
  return dashboardSqlite
    .prepare(`SELECT * FROM operator_audit_log ORDER BY id DESC LIMIT ?`)
    .all(limit);
}

// AtlasBridge operational DB (read-only) — sessions, prompts, audit
let _abDb: Database.Database | null = null;
export function getAtlasBridgeDb(): Database.Database | null {
  if (_abDb) return _abDb;
  const abPath = getAtlasBridgeDbPath();
  try {
    _abDb = new Database(abPath, { readonly: true });
    return _abDb;
  } catch {
    console.warn(`AtlasBridge DB not found at ${abPath} — operational data unavailable`);
    return null;
  }
}
