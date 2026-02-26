import { sqliteTable, text, integer } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export type RiskLevel = "low" | "medium" | "high" | "critical";
export type SessionStatus = "running" | "stopped" | "paused";
export type CIStatus = "pass" | "fail" | "unknown";
export type AutonomyMode = "Off" | "Assist" | "Full";
export type IntegrityStatus = "Verified" | "Warning" | "Failed";
export type PromptType = "yes_no" | "confirm_enter" | "numbered_choice" | "free_text" | "multi_select";
export type PromptDecision = "auto" | "human" | "escalated";

export interface AISafetyMetrics {
  modelTrustScore: number;
  hallucinationRate: number;
  promptInjectionBlocked: number;
  biasDetections: number;
  safetyOverrides: number;
  avgConfidence: number;
  humanOverrideRate: number;
  trend: "improving" | "stable" | "declining";
}

export interface ComplianceMetrics {
  overallScore: number;
  frameworkScores: { framework: string; score: number; maxScore: number }[];
  openFindings: number;
  resolvedLast30d: number;
  nextAuditDays: number;
  policyAdherence: number;
}

export interface OperationalMetrics {
  avgResponseTime: number;
  uptime: number;
  errorRate: number;
  throughput: number;
  p95Latency: number;
  activeIntegrations: number;
}

export interface MetricInsight {
  id: string;
  category: "safety" | "compliance" | "operations" | "risk";
  type: "recommendation" | "warning" | "positive";
  title: string;
  description: string;
  impact: "high" | "medium" | "low";
  actionable: boolean;
}

export interface OverviewData {
  activeSessions: number;
  lastEventTimestamp: string;
  escalationRate: number;
  autonomyMode: AutonomyMode;
  highRiskEvents: number;
  integrityStatus: IntegrityStatus;
  recentActivity: ActivityEvent[];
  topRulesTriggered: RuleTriggered[];
  riskBreakdown: { low: number; medium: number; high: number; critical: number };
  aiSafety: AISafetyMetrics;
  compliance: ComplianceMetrics;
  operational: OperationalMetrics;
  insights: MetricInsight[];
}

export interface ActivityEvent {
  id: string;
  timestamp: string;
  type: string;
  message: string;
  riskLevel: RiskLevel;
  sessionId?: string;
}

export interface RuleTriggered {
  ruleId: string;
  ruleName: string;
  count: number;
  lastTriggered: string;
}

export interface Session {
  id: string;
  tool: string;
  startTime: string;
  lastActivity: string;
  status: SessionStatus;
  riskLevel: RiskLevel;
  escalationsCount: number;
  ciSnapshot: CIStatus;
}

export interface SessionDetail extends Session {
  metadata: Record<string, string>;
  prompts: PromptEntry[];
  decisionTrace: TraceEntry[];
  explainPanel: string;
  rawView: string;
}

export interface PromptEntry {
  id: string;
  type: PromptType;
  confidence: number;
  decision: PromptDecision;
  actionTaken: string;
  timestamp: string;
  sessionId: string;
  content: string;
}

export interface TraceEntry {
  id: string;
  hash: string;
  stepIndex: number;
  riskLevel: RiskLevel;
  ruleMatched: string;
  action: string;
  timestamp: string;
  sessionId: string;
}

export interface IntegrityResult {
  component: string;
  status: IntegrityStatus;
  hash: string;
  lastChecked: string;
  details: string;
}

export interface IntegrityData {
  overallStatus: IntegrityStatus;
  lastVerifiedAt: string;
  results: IntegrityResult[];
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  riskLevel: RiskLevel;
  sessionId: string;
  promptType: PromptType;
  actionTaken: string;
  message: string;
  hashVerified: boolean;
}

export interface SettingsData {
  configPath: string;
  dbPath: string;
  tracePath: string;
  version: string;
  environment: string;
  featureFlags: Record<string, boolean>;
}

export interface VersionInfo {
  current: string;
  latest: string | null;
  updateAvailable: boolean;
  upgradeCommand: string;
}

// --- Dashboard settings tables (read-write, dashboard.db) ---

export const users = sqliteTable("users", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  externalId: text("external_id").notNull().unique(),
  username: text("username").notNull().unique(),
  email: text("email").notNull(),
  displayName: text("display_name").notNull(),
  role: text("role").notNull().default("Viewer"),
  status: text("status").notNull().default("pending"),
  mfaStatus: text("mfa_status").notNull().default("disabled"),
  lastActive: text("last_active"),
  createdAt: text("created_at").notNull().default(sql`(datetime('now'))`),
  groups: text("groups", { mode: "json" }).notNull().default("[]").$type<string[]>(),
  loginMethod: text("login_method").notNull().default("SSO"),
});

export const insertUserSchema = createInsertSchema(users).omit({ id: true, createdAt: true });
export type InsertUser = z.infer<typeof insertUserSchema>;
export type User = typeof users.$inferSelect;

export const groups = sqliteTable("groups", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  externalId: text("external_id").notNull().unique(),
  name: text("name").notNull(),
  description: text("description").notNull().default(""),
  memberCount: integer("member_count").notNull().default(0),
  roles: text("roles", { mode: "json" }).notNull().default("[]").$type<string[]>(),
  permissionLevel: text("permission_level").notNull().default("read"),
  createdAt: text("created_at").notNull().default(sql`(datetime('now'))`),
  syncSource: text("sync_source").notNull().default("Manual"),
  lastSynced: text("last_synced"),
});

export const insertGroupSchema = createInsertSchema(groups).omit({ id: true, createdAt: true });
export type InsertGroup = z.infer<typeof insertGroupSchema>;
export type Group = typeof groups.$inferSelect;

export const roles = sqliteTable("roles", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  externalId: text("external_id").notNull().unique(),
  name: text("name").notNull(),
  description: text("description").notNull().default(""),
  permissions: text("permissions", { mode: "json" }).notNull().default("[]").$type<string[]>(),
  isSystem: integer("is_system", { mode: "boolean" }).notNull().default(false),
  memberCount: integer("member_count").notNull().default(0),
  createdAt: text("created_at").notNull().default(sql`(datetime('now'))`),
});

export const insertRoleSchema = createInsertSchema(roles).omit({ id: true, createdAt: true });
export type InsertRole = z.infer<typeof insertRoleSchema>;
export type Role = typeof roles.$inferSelect;

export const apiKeys = sqliteTable("api_keys", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  externalId: text("external_id").notNull().unique(),
  name: text("name").notNull(),
  prefix: text("prefix").notNull(),
  scopes: text("scopes", { mode: "json" }).notNull().default("[]").$type<string[]>(),
  status: text("status").notNull().default("active"),
  createdBy: text("created_by").notNull(),
  createdAt: text("created_at").notNull().default(sql`(datetime('now'))`),
  expiresAt: text("expires_at"),
  lastUsed: text("last_used"),
  rateLimit: integer("rate_limit").notNull().default(100),
});

export const insertApiKeySchema = createInsertSchema(apiKeys).omit({ id: true, createdAt: true });
export type InsertApiKey = z.infer<typeof insertApiKeySchema>;
export type ApiKey = typeof apiKeys.$inferSelect;

export const securityPolicies = sqliteTable("security_policies", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  externalId: text("external_id").notNull().unique(),
  name: text("name").notNull(),
  category: text("category").notNull(),
  description: text("description").notNull(),
  enabled: integer("enabled", { mode: "boolean" }).notNull().default(true),
  value: text("value").notNull(),
  severity: text("severity").notNull().default("info"),
});

export const insertSecurityPolicySchema = createInsertSchema(securityPolicies).omit({ id: true });
export type InsertSecurityPolicy = z.infer<typeof insertSecurityPolicySchema>;
export type SecurityPolicy = typeof securityPolicies.$inferSelect;

export const notifications = sqliteTable("notifications", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  externalId: text("external_id").notNull().unique(),
  channel: text("channel").notNull(),
  name: text("name").notNull(),
  enabled: integer("enabled", { mode: "boolean" }).notNull().default(true),
  destination: text("destination").notNull(),
  events: text("events", { mode: "json" }).notNull().default("[]").$type<string[]>(),
  minSeverity: text("min_severity").notNull().default("info"),
  lastDelivered: text("last_delivered"),
});

export const insertNotificationSchema = createInsertSchema(notifications).omit({ id: true });
export type InsertNotification = z.infer<typeof insertNotificationSchema>;
export type Notification = typeof notifications.$inferSelect;

export const ipAllowlist = sqliteTable("ip_allowlist", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  externalId: text("external_id").notNull().unique(),
  cidr: text("cidr").notNull(),
  label: text("label").notNull(),
  addedBy: text("added_by").notNull(),
  addedAt: text("added_at").notNull().default(sql`(datetime('now'))`),
  lastHit: text("last_hit"),
});

export const insertIpAllowlistSchema = createInsertSchema(ipAllowlist).omit({ id: true, addedAt: true });
export type InsertIpAllowlist = z.infer<typeof insertIpAllowlistSchema>;
export type IpAllowlistEntry = typeof ipAllowlist.$inferSelect;

export const repoConnections = sqliteTable("repo_connections", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  provider: text("provider").notNull(),
  owner: text("owner").notNull(),
  repo: text("repo").notNull(),
  branch: text("branch").notNull().default("main"),
  url: text("url").notNull(),
  status: text("status").notNull().default("connected"),
  accessToken: text("access_token"),
  connectedBy: text("connected_by").notNull(),
  connectedAt: text("connected_at").notNull().default(sql`(datetime('now'))`),
  lastSynced: text("last_synced"),
  complianceLevel: text("compliance_level").notNull().default("standard"),
  complianceScore: integer("compliance_score"),
});

export const insertRepoConnectionSchema = createInsertSchema(repoConnections).omit({ id: true, connectedAt: true });
export type InsertRepoConnection = z.infer<typeof insertRepoConnectionSchema>;
export type RepoConnection = typeof repoConnections.$inferSelect;

export const complianceScans = sqliteTable("compliance_scans", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  repoConnectionId: integer("repo_connection_id").notNull(),
  scanDate: text("scan_date").notNull().default(sql`(datetime('now'))`),
  complianceLevel: text("compliance_level").notNull(),
  overallScore: integer("overall_score").notNull(),
  categories: text("categories", { mode: "json" }).notNull(),
  suggestions: text("suggestions", { mode: "json" }).notNull(),
});

export const insertComplianceScanSchema = createInsertSchema(complianceScans).omit({ id: true, scanDate: true });
export type InsertComplianceScan = z.infer<typeof insertComplianceScanSchema>;
export type ComplianceScan = typeof complianceScans.$inferSelect;

export type UserStatus = "active" | "inactive" | "suspended" | "pending";
export type MfaStatus = "enabled" | "disabled" | "enforced";
export type ApiKeyStatus = "active" | "revoked" | "expired";
export type SsoProvider = "saml" | "oidc" | "ldap" | "none";
export type ComplianceFramework = "SOC2" | "ISO27001" | "HIPAA" | "GDPR" | "PCI-DSS" | "FedRAMP";
export type NotificationChannel = "slack" | "email" | "webhook" | "pagerduty" | "opsgenie";

export interface OrgProfile {
  id: string;
  name: string;
  slug: string;
  planTier: string;
  createdAt: string;
  owner: string;
  domain: string;
  maxSeats: number;
  usedSeats: number;
}

export interface RbacPermission {
  id: string;
  resource: string;
  actions: string[];
  description: string;
  category: string;
}

export interface SsoConfig {
  provider: SsoProvider;
  enabled: boolean;
  entityId: string;
  ssoUrl: string;
  certificate: string;
  autoProvision: boolean;
  defaultRole: string;
  allowedDomains: string[];
  jitProvisioning: boolean;
  forceAuth: boolean;
  sessionDuration: number;
}

export interface ComplianceConfig {
  frameworks: ComplianceFramework[];
  auditRetentionDays: number;
  traceRetentionDays: number;
  sessionRetentionDays: number;
  dataResidency: string;
  encryptionAtRest: boolean;
  encryptionInTransit: boolean;
  autoRedaction: boolean;
  dlpEnabled: boolean;
  lastAuditDate: string;
  nextAuditDate: string;
}

export interface SessionPolicyConfig {
  maxConcurrentSessions: number;
  sessionTimeoutMinutes: number;
  inactivityTimeoutMinutes: number;
  autoTerminateOnEscalation: boolean;
  requireApprovalAboveRisk: string;
  maxEscalationsPerSession: number;
  recordAllSessions: boolean;
  allowedTools: string[];
  blockedTools: string[];
  riskAutoEscalationThreshold: number;
}

export interface OrgSettingsData {
  organization: OrgProfile;
  roles: Role[];
  permissions: RbacPermission[];
  groups: Group[];
  users: User[];
  apiKeys: ApiKey[];
  sso: SsoConfig;
  securityPolicies: SecurityPolicy[];
  compliance: ComplianceConfig;
  notifications: Notification[];
  sessionPolicy: SessionPolicyConfig;
  ipAllowlist: IpAllowlistEntry[];
}

export interface ComplianceSuggestion {
  id: string;
  category: string;
  title: string;
  description: string;
  impact: "critical" | "recommended" | "nice-to-have";
  status: "pass" | "fail" | "warning";
  details?: string;
}

export interface ComplianceCategoryScore {
  name: string;
  score: number;
  maxScore: number;
  checks: { name: string; passed: boolean; detail: string }[];
}

export interface ComplianceScanResult {
  overallScore: number;
  complianceLevel: string;
  categories: ComplianceCategoryScore[];
  suggestions: ComplianceSuggestion[];
  scannedAt: string;
}
