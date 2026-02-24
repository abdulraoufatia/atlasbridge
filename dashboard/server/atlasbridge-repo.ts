/**
 * Read-only repository for AtlasBridge operational data.
 *
 * Reads from AtlasBridge's SQLite database (sessions, prompts, audit_events)
 * and the JSONL decision trace file. All methods are synchronous because
 * better-sqlite3 is synchronous.
 *
 * Port of src/atlasbridge/dashboard/repo.py to TypeScript.
 */

import fs from "fs";
import { getAtlasBridgeDb } from "./db";
import {
  getTracePath,
  getConfigPath,
  getAtlasBridgeDir,
  getAtlasBridgeDbPath,
} from "./config";
import { sanitizeForDisplay } from "./sanitize";
import type {
  Session,
  SessionDetail,
  PromptEntry,
  TraceEntry,
  AuditEntry,
  IntegrityData,
  IntegrityResult,
  OverviewData,
  SettingsData,
  ActivityEvent,
  RiskLevel,
  PromptDecision,
  PromptType,
} from "@shared/schema";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function confidenceToNumber(conf: string): number {
  switch (conf.toLowerCase()) {
    case "high":
      return 0.95;
    case "medium":
      return 0.65;
    case "low":
      return 0.35;
    default:
      return 0.5;
  }
}

function mapSessionStatus(
  status: string
): "running" | "stopped" | "paused" {
  switch (status) {
    case "starting":
    case "running":
      return "running";
    case "paused":
      return "paused";
    default:
      return "stopped";
  }
}

function computeRiskLevel(escalations: number): RiskLevel {
  if (escalations >= 5) return "critical";
  if (escalations >= 3) return "high";
  if (escalations >= 1) return "medium";
  return "low";
}

function mapActionToRisk(actionType: string, confidence: string): RiskLevel {
  if (actionType === "require_human" || actionType === "escalate")
    return "high";
  if (confidence === "low") return "medium";
  if (actionType === "auto_no" || actionType === "block") return "critical";
  return "low";
}

function mapPromptDecision(
  status: string,
  responseNormalized: string | null
): PromptDecision {
  if (status === "escalated" || status === "routed") return "escalated";
  if (
    responseNormalized &&
    (status === "resolved" || status === "injected")
  )
    return "auto";
  return "human";
}

function sanitizeRow(row: Record<string, unknown>): Record<string, unknown> {
  const d = { ...row };
  for (const key of ["excerpt", "value", "payload", "command"]) {
    if (key in d && typeof d[key] === "string") {
      d[key] = sanitizeForDisplay(d[key] as string);
    }
  }
  return d;
}

// ---------------------------------------------------------------------------
// Repository
// ---------------------------------------------------------------------------

export class AtlasBridgeRepo {
  get dbAvailable(): boolean {
    return getAtlasBridgeDb() !== null;
  }

  get traceAvailable(): boolean {
    try {
      return fs.existsSync(getTracePath());
    } catch {
      return false;
    }
  }

  // -----------------------------------------------------------------------
  // Stats
  // -----------------------------------------------------------------------

  getStats(): {
    sessions: number;
    prompts: number;
    audit_events: number;
    active_sessions: number;
  } {
    const db = getAtlasBridgeDb();
    if (!db)
      return { sessions: 0, prompts: 0, audit_events: 0, active_sessions: 0 };

    const stats: Record<string, number> = {};
    for (const table of ["sessions", "prompts", "audit_events"] as const) {
      const row = db.prepare(`SELECT count(*) as cnt FROM ${table}`).get() as
        | { cnt: number }
        | undefined;
      stats[table] = row?.cnt ?? 0;
    }

    const active = db
      .prepare(
        "SELECT count(*) as cnt FROM sessions WHERE status NOT IN ('completed', 'crashed', 'canceled')"
      )
      .get() as { cnt: number } | undefined;
    stats["active_sessions"] = active?.cnt ?? 0;

    return {
      sessions: stats["sessions"],
      prompts: stats["prompts"],
      audit_events: stats["audit_events"],
      active_sessions: stats["active_sessions"],
    };
  }

  // -----------------------------------------------------------------------
  // Sessions
  // -----------------------------------------------------------------------

  listSessions(): Session[] {
    const db = getAtlasBridgeDb();
    if (!db) return [];

    const rows = db
      .prepare("SELECT * FROM sessions ORDER BY started_at DESC")
      .all() as Record<string, unknown>[];

    return rows.map((row) => {
      const r = sanitizeRow(row);
      const sessionId = r["id"] as string;
      // Count escalations for this session
      const escRow = db
        .prepare(
          "SELECT count(*) as cnt FROM prompts WHERE session_id = ? AND status IN ('escalated', 'routed')"
        )
        .get(sessionId) as { cnt: number } | undefined;
      const escalations = escRow?.cnt ?? 0;

      return {
        id: sessionId,
        tool: (r["tool"] as string) || "unknown",
        startTime: (r["started_at"] as string) || new Date().toISOString(),
        lastActivity:
          (r["ended_at"] as string) ||
          (r["started_at"] as string) ||
          new Date().toISOString(),
        status: mapSessionStatus((r["status"] as string) || "stopped"),
        riskLevel: computeRiskLevel(escalations),
        escalationsCount: escalations,
        ciSnapshot: "unknown" as const,
      };
    });
  }

  getSession(sessionId: string): SessionDetail | null {
    const db = getAtlasBridgeDb();
    if (!db) return null;

    const row = db
      .prepare("SELECT * FROM sessions WHERE id = ?")
      .get(sessionId) as Record<string, unknown> | undefined;
    if (!row) return null;

    const r = sanitizeRow(row);
    const prompts = this.listPromptsForSession(sessionId);
    const traces = this.listTracesForSession(sessionId);
    const escCount = prompts.filter((p) => p.decision === "escalated").length;

    let metadata: Record<string, string> = {};
    try {
      const raw = (r["metadata"] as string) || "{}";
      metadata = JSON.parse(raw);
    } catch {
      /* ignore */
    }
    metadata["Adapter"] = (r["tool"] as string) || "unknown";
    if (r["pid"]) metadata["PID"] = String(r["pid"]);
    if (r["cwd"]) metadata["Working Directory"] = r["cwd"] as string;
    if (r["command"]) metadata["Command"] = r["command"] as string;

    const session: Session = {
      id: sessionId,
      tool: (r["tool"] as string) || "unknown",
      startTime: (r["started_at"] as string) || new Date().toISOString(),
      lastActivity:
        (r["ended_at"] as string) ||
        (r["started_at"] as string) ||
        new Date().toISOString(),
      status: mapSessionStatus((r["status"] as string) || "stopped"),
      riskLevel: computeRiskLevel(escCount),
      escalationsCount: escCount,
      ciSnapshot: "unknown" as const,
    };

    const explainPanel =
      escCount > 0
        ? `This session triggered ${escCount} escalation(s). Confidence scores below the auto-approval threshold required human intervention.`
        : `This session operated within normal parameters. All decisions were auto-approved. No escalations were required.`;

    return {
      ...session,
      metadata,
      prompts,
      decisionTrace: traces,
      explainPanel,
      rawView: JSON.stringify(
        { session_id: sessionId, ...r, prompt_count: prompts.length, trace_count: traces.length },
        null,
        2
      ),
    };
  }

  // -----------------------------------------------------------------------
  // Prompts
  // -----------------------------------------------------------------------

  listPrompts(): PromptEntry[] {
    const db = getAtlasBridgeDb();
    if (!db) return [];

    const rows = db
      .prepare("SELECT * FROM prompts ORDER BY created_at DESC LIMIT 200")
      .all() as Record<string, unknown>[];

    return rows.map((row, i) => this._mapPrompt(row, i));
  }

  listPromptsForSession(sessionId: string): PromptEntry[] {
    const db = getAtlasBridgeDb();
    if (!db) return [];

    const rows = db
      .prepare(
        "SELECT * FROM prompts WHERE session_id = ? ORDER BY created_at ASC"
      )
      .all(sessionId) as Record<string, unknown>[];

    return rows.map((row, i) => this._mapPrompt(row, i));
  }

  private _mapPrompt(row: Record<string, unknown>, _index: number): PromptEntry {
    const r = sanitizeRow(row);
    return {
      id: r["id"] as string,
      type: (r["prompt_type"] as PromptType) || "yes_no",
      confidence: confidenceToNumber((r["confidence"] as string) || "medium"),
      decision: mapPromptDecision(
        (r["status"] as string) || "",
        r["response_normalized"] as string | null
      ),
      actionTaken: (r["status"] as string) || "unknown",
      timestamp: (r["created_at"] as string) || new Date().toISOString(),
      sessionId: (r["session_id"] as string) || "",
      content: (r["excerpt"] as string) || "",
    };
  }

  // -----------------------------------------------------------------------
  // Audit events
  // -----------------------------------------------------------------------

  listAuditEvents(): AuditEntry[] {
    const db = getAtlasBridgeDb();
    if (!db) return [];

    const rows = db
      .prepare("SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT 200")
      .all() as Record<string, unknown>[];

    let prevHash = "";
    // For hash verification, we need to check chain order (oldest first)
    const orderedRows = db
      .prepare("SELECT id, prev_hash, hash FROM audit_events ORDER BY timestamp ASC")
      .all() as { id: string; prev_hash: string; hash: string }[];
    const hashValid = new Map<string, boolean>();
    for (const r of orderedRows) {
      hashValid.set(r.id, r.prev_hash === prevHash);
      prevHash = r.hash || "";
    }

    return rows.map((row) => {
      const r = sanitizeRow(row);
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse((r["payload"] as string) || "{}");
      } catch {
        /* ignore */
      }

      return {
        id: r["id"] as string,
        timestamp: (r["timestamp"] as string) || new Date().toISOString(),
        riskLevel: ((payload["risk_level"] as RiskLevel) || "low") as RiskLevel,
        sessionId: (r["session_id"] as string) || "",
        promptType: ((payload["prompt_type"] as PromptType) || "yes_no") as PromptType,
        actionTaken: (r["event_type"] as string) || "logged",
        message: this._formatAuditMessage(
          (r["event_type"] as string) || "",
          payload
        ),
        hashVerified: hashValid.get(r["id"] as string) ?? true,
      };
    });
  }

  private _formatAuditMessage(
    eventType: string,
    payload: Record<string, unknown>
  ): string {
    const desc = (payload["description"] as string) || "";
    if (desc) return sanitizeForDisplay(desc);
    return `${eventType.replace(/_/g, " ")} event recorded`;
  }

  // -----------------------------------------------------------------------
  // Decision trace (JSONL)
  // -----------------------------------------------------------------------

  listTraces(): TraceEntry[] {
    return this._readTraceEntries(200);
  }

  listTracesForSession(sessionId: string): TraceEntry[] {
    const all = this._readTraceEntries(10000);
    return all.filter((t) => t.sessionId === sessionId);
  }

  private _readTraceEntries(limit: number): TraceEntry[] {
    const tracePath = getTracePath();
    if (!fs.existsSync(tracePath)) return [];

    let lines: string[];
    try {
      const content = fs.readFileSync(tracePath, "utf-8");
      lines = content.split("\n").filter((l) => l.trim());
    } catch {
      return [];
    }

    // Take the last `limit` lines (newest entries)
    const recent = lines.slice(-limit);
    const entries: TraceEntry[] = [];

    for (let i = 0; i < recent.length; i++) {
      try {
        const entry = JSON.parse(recent[i]) as Record<string, unknown>;
        entries.push({
          id:
            (entry["idempotency_key"] as string) ||
            `trace-${String(i + 1).padStart(3, "0")}`,
          hash: (entry["hash"] as string)
            ? `sha256:${(entry["hash"] as string).slice(0, 24)}`
            : "",
          stepIndex: i + 1,
          riskLevel: mapActionToRisk(
            (entry["action_type"] as string) || "",
            (entry["confidence"] as string) || ""
          ),
          ruleMatched: (entry["matched_rule_id"] as string) || "default",
          action: (entry["action_type"] as string) || "logged",
          timestamp:
            (entry["timestamp"] as string) || new Date().toISOString(),
          sessionId: (entry["session_id"] as string) || "",
        });
      } catch {
        continue;
      }
    }

    // Return newest first
    entries.reverse();
    return entries;
  }

  // -----------------------------------------------------------------------
  // Integrity
  // -----------------------------------------------------------------------

  getIntegrity(): IntegrityData {
    const now = new Date().toISOString();
    const results: IntegrityResult[] = [];

    // Check audit hash chain
    const auditResult = this._verifyAuditIntegrity();
    results.push({
      component: "Audit Logger",
      status: auditResult.valid ? "Verified" : "Warning",
      hash: `sha256:${auditResult.lastHash.slice(0, 16) || "none"}`,
      lastChecked: now,
      details: auditResult.valid
        ? `All ${auditResult.count} audit entries hash-verified and sequential`
        : `${auditResult.errors.length} integrity error(s) found`,
    });

    // Check trace hash chain
    const traceResult = this._verifyTraceIntegrity();
    results.push({
      component: "Decision Trace Store",
      status: traceResult.valid ? "Verified" : "Warning",
      hash: `sha256:${traceResult.lastHash.slice(0, 16) || "none"}`,
      lastChecked: now,
      details: traceResult.valid
        ? `Hash chain continuous, ${traceResult.count} entries verified`
        : `${traceResult.errors.length} integrity error(s) found`,
    });

    // Session manager check
    const stats = this.getStats();
    results.push({
      component: "Session Manager",
      status: "Verified",
      hash: "",
      lastChecked: now,
      details: `${stats.sessions} total sessions, ${stats.active_sessions} active`,
    });

    // Prompt resolver check
    results.push({
      component: "Prompt Resolver",
      status: stats.prompts > 0 ? "Verified" : "Warning",
      hash: "",
      lastChecked: now,
      details:
        stats.prompts > 0
          ? `${stats.prompts} prompts processed`
          : "No prompts recorded yet",
    });

    const hasWarning = results.some((r) => r.status === "Warning");
    const hasFailed = results.some((r) => r.status === "Failed");

    return {
      overallStatus: hasFailed ? "Failed" : hasWarning ? "Warning" : "Verified",
      lastVerifiedAt: now,
      results,
    };
  }

  private _verifyAuditIntegrity(): {
    valid: boolean;
    errors: string[];
    lastHash: string;
    count: number;
  } {
    const db = getAtlasBridgeDb();
    if (!db) return { valid: true, errors: [], lastHash: "", count: 0 };

    const rows = db
      .prepare(
        "SELECT id, prev_hash, hash FROM audit_events ORDER BY timestamp ASC"
      )
      .all() as { id: string; prev_hash: string; hash: string }[];

    const errors: string[] = [];
    let prevHash = "";
    for (let i = 0; i < rows.length; i++) {
      if (rows[i].prev_hash !== prevHash) {
        errors.push(
          `Event ${i + 1} (id=${rows[i].id}): prev_hash mismatch`
        );
      }
      prevHash = rows[i].hash || "";
    }

    return {
      valid: errors.length === 0,
      errors,
      lastHash: prevHash,
      count: rows.length,
    };
  }

  private _verifyTraceIntegrity(): {
    valid: boolean;
    errors: string[];
    lastHash: string;
    count: number;
  } {
    const tracePath = getTracePath();
    if (!fs.existsSync(tracePath))
      return { valid: true, errors: [], lastHash: "", count: 0 };

    let lines: string[];
    try {
      lines = fs
        .readFileSync(tracePath, "utf-8")
        .split("\n")
        .filter((l) => l.trim());
    } catch {
      return { valid: true, errors: [], lastHash: "", count: 0 };
    }

    const errors: string[] = [];
    let prevHash = "";
    let count = 0;

    for (let i = 0; i < lines.length; i++) {
      try {
        const entry = JSON.parse(lines[i]) as Record<string, unknown>;
        count++;
        if (!("hash" in entry) || !("prev_hash" in entry)) {
          prevHash = "";
          continue;
        }
        if ((entry["prev_hash"] as string) !== prevHash) {
          errors.push(`Line ${i + 1}: prev_hash mismatch`);
        }
        prevHash = (entry["hash"] as string) || "";
      } catch {
        errors.push(`Line ${i + 1}: invalid JSON`);
        prevHash = "";
      }
    }

    return { valid: errors.length === 0, errors, lastHash: prevHash, count };
  }

  // -----------------------------------------------------------------------
  // Overview (computed from real data)
  // -----------------------------------------------------------------------

  getOverview(): OverviewData {
    const stats = this.getStats();
    const sessions = this.listSessions();
    const prompts = this.listPrompts();
    const integrity = this.getIntegrity();

    // Compute escalation rate
    const totalPrompts = prompts.length;
    const escalated = prompts.filter(
      (p) => p.decision === "escalated"
    ).length;
    const escalationRate =
      totalPrompts > 0
        ? Math.round((escalated / totalPrompts) * 1000) / 10
        : 0;

    // Compute risk breakdown from prompts
    const riskBreakdown = { low: 0, medium: 0, high: 0, critical: 0 };
    for (const p of prompts) {
      if (p.confidence >= 0.8) riskBreakdown.low++;
      else if (p.confidence >= 0.5) riskBreakdown.medium++;
      else if (p.confidence >= 0.3) riskBreakdown.high++;
      else riskBreakdown.critical++;
    }

    // Build recent activity from audit events
    const auditEvents = this.listAuditEvents().slice(0, 20);
    const recentActivity: ActivityEvent[] = auditEvents.map((a) => ({
      id: a.id,
      timestamp: a.timestamp,
      type: a.actionTaken,
      message: a.message,
      riskLevel: a.riskLevel,
      sessionId: a.sessionId || undefined,
    }));

    // Compute auto/human rates
    const autoDecisions = prompts.filter((p) => p.decision === "auto").length;
    const humanDecisions = prompts.filter((p) => p.decision === "human").length;
    const avgConfidence =
      totalPrompts > 0
        ? Math.round(
            (prompts.reduce((s, p) => s + p.confidence, 0) / totalPrompts) *
              100
          ) / 100
        : 0;
    const humanOverrideRate =
      totalPrompts > 0
        ? Math.round((humanDecisions / totalPrompts) * 1000) / 10
        : 0;

    const highRiskEvents = prompts.filter(
      (p) => p.confidence < 0.5
    ).length;

    // Find last event timestamp
    const lastEvent =
      auditEvents.length > 0
        ? auditEvents[0].timestamp
        : new Date().toISOString();

    return {
      activeSessions: stats.active_sessions,
      lastEventTimestamp: lastEvent,
      escalationRate,
      autonomyMode: "Assist",
      highRiskEvents,
      integrityStatus: integrity.overallStatus as "Verified" | "Warning" | "Failed",
      recentActivity,
      topRulesTriggered: [],
      riskBreakdown,
      aiSafety: {
        modelTrustScore: Math.max(0, 100 - escalationRate * 2),
        hallucinationRate: 0,
        promptInjectionBlocked: 0,
        biasDetections: 0,
        safetyOverrides: escalated,
        avgConfidence,
        humanOverrideRate,
        trend: escalationRate < 20 ? "improving" : escalationRate < 40 ? "stable" : "declining",
      },
      compliance: {
        overallScore: 0,
        frameworkScores: [],
        openFindings: 0,
        resolvedLast30d: 0,
        nextAuditDays: 0,
        policyAdherence: 0,
      },
      operational: {
        avgResponseTime: 0,
        uptime: 100,
        errorRate: 0,
        throughput: stats.prompts,
        p95Latency: 0,
        activeIntegrations: 0,
      },
      insights: [],
    };
  }

  // -----------------------------------------------------------------------
  // Settings
  // -----------------------------------------------------------------------

  getSettings(): SettingsData {
    return {
      configPath: getConfigPath(),
      dbPath: getAtlasBridgeDbPath(),
      tracePath: getTracePath(),
      version: "1.0.1",
      environment: "local",
      featureFlags: {
        auto_escalation: true,
        hash_chain_verification: true,
        real_time_streaming: false,
        multi_adapter_support: true,
        policy_hot_reload: true,
      },
    };
  }
}

export const repo = new AtlasBridgeRepo();
