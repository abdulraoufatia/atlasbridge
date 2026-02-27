import type { Express } from "express";
import { createServer, type Server } from "http";
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { registerOperatorRoutes } from "./routes/operator";
import { WebSocketServer, WebSocket } from "ws";
import { repo } from "./atlasbridge-repo";
import { storage } from "./storage";
import { seedDatabase } from "./seed";
import { runComplianceScan } from "./compliance-engine";
import {
  generateEvidenceJSON, generateEvidenceCSV, generateFullBundle,
  computeGovernanceScore, compliancePacks, listGeneratedBundles, addGeneratedBundle,
} from "./evidence-engine";
import { handleTerminalConnection } from "./terminal";
import { requireCsrf } from "./middleware/csrf";
import { operatorRateLimiter } from "./middleware/rate-limit";
import { insertOperatorAuditLog } from "./db";
import { getConfigPath } from "./config";
import { parse as parseTOML, stringify as stringifyTOML } from "smol-toml";

// ---------------------------------------------------------------------------
// TOML config helpers — read/write atlasbridge config.toml directly
// ---------------------------------------------------------------------------

function readAtlasBridgeConfig(): Record<string, unknown> {
  const cfgPath = getConfigPath();
  if (!fs.existsSync(cfgPath)) return {};
  try {
    return parseTOML(fs.readFileSync(cfgPath, "utf8")) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function writeAtlasBridgeConfig(data: Record<string, unknown>): void {
  const cfgPath = getConfigPath();
  fs.mkdirSync(path.dirname(cfgPath), { recursive: true });
  if (!data.config_version) data.config_version = 1;
  fs.writeFileSync(cfgPath, stringifyTOML(data), { encoding: "utf8", mode: 0o600 });
}

const DEFAULT_POLICY_YAML = `\
policy_version: "1"
name: "claude-code-dev"
autonomy_mode: full

rules:

  - id: "deny-credentials"
    description: "Never auto-reply to credential prompts"
    match:
      prompt_type: [free_text]
      contains: "password|token|api.?key|secret|passphrase"
      contains_is_regex: true
      min_confidence: low
    action:
      type: deny
      reason: "Credential prompts are never auto-replied."

  - id: "deny-force-push"
    description: "Never auto-approve git force-push"
    match:
      contains: "force.push|force push"
      contains_is_regex: true
      min_confidence: low
    action:
      type: deny
      reason: "Force-push requires manual approval."

  - id: "require-human-destructive"
    description: "Escalate destructive operations to human"
    match:
      contains: "delete|destroy|drop table|purge|wipe|truncate|rm -rf"
      contains_is_regex: true
      min_confidence: low
    action:
      type: require_human
      message: "Destructive operation detected — please review."

  - id: "require-human-are-you-sure"
    description: "Escalate explicit confirmation prompts"
    match:
      contains: "are you sure"
      contains_is_regex: false
      min_confidence: low
    action:
      type: require_human
      message: "Explicit confirmation required — please review."

  - id: "claude-code-yes-no"
    description: "Auto-allow yes/no permission prompts"
    match:
      prompt_type: [yes_no]
      min_confidence: medium
    action:
      type: auto_reply
      value: "y"
      constraints:
        allowed_choices: ["y", "n"]

  - id: "claude-code-confirm-enter"
    description: "Auto-confirm press-enter prompts"
    match:
      prompt_type: [confirm_enter]
      min_confidence: medium
    action:
      type: auto_reply
      value: "\\n"

  - id: "claude-code-select-first"
    description: "Auto-select option 1 on multiple-choice prompts"
    match:
      prompt_type: [multiple_choice]
      min_confidence: medium
    action:
      type: auto_reply
      value: "1"

  - id: "claude-code-tool-use"
    description: "Auto-approve tool_use permission prompts"
    match:
      prompt_type: [tool_use]
      min_confidence: medium
    action:
      type: auto_reply
      value: "1"

  - id: "claude-code-free-text-medium"
    description: "Auto-approve medium-confidence free_text prompts"
    match:
      prompt_type: [free_text]
      min_confidence: medium
    action:
      type: auto_reply
      value: "1"

  - id: "catch-all"
    description: "Unmatched prompts go to human"
    match: {}
    action:
      type: require_human
      message: "No policy rule matched — please review and respond."

defaults:
  no_match: require_human
  low_confidence: require_human
`;

function ensureAutopilotReady(): void {
  const cfgDir = path.dirname(getConfigPath());
  fs.mkdirSync(cfgDir, { recursive: true });

  // Write default policy if none exists
  const policyPath = path.join(cfgDir, "policy.yaml");
  if (!fs.existsSync(policyPath)) {
    fs.writeFileSync(policyPath, DEFAULT_POLICY_YAML, { encoding: "utf8", mode: 0o600 });
  }

  // Ensure autopilot state is running
  const statePath = path.join(cfgDir, "autopilot_state.json");
  let state: Record<string, unknown> = {};
  try { state = JSON.parse(fs.readFileSync(statePath, "utf8")); } catch { /* fresh state */ }
  if (state.state !== "running") {
    state.state = "running";
    fs.writeFileSync(statePath, JSON.stringify(state), { encoding: "utf8", mode: 0o600 });
  }
}

// Static org settings (stored in dashboard DB via seed, not in AtlasBridge DB)
import type { RbacPermission, OrgProfile, SsoConfig, ComplianceConfig, SessionPolicyConfig } from "@shared/schema";

const orgSettingsStatic: {
  organization: OrgProfile;
  permissions: RbacPermission[];
  sso: SsoConfig;
  compliance: ComplianceConfig;
  sessionPolicy: SessionPolicyConfig;
} = {
  organization: {
    id: "org-ab12cd34ef56",
    name: "AtlasBridge Operations",
    slug: "atlasbridge-ops",
    planTier: "Enterprise",
    createdAt: new Date(Date.now() - 180 * 86400000).toISOString(),
    owner: "admin@atlasbridge.local",
    domain: "atlasbridge.local",
    maxSeats: 50,
    usedSeats: 18,
  },
  permissions: [
    { id: "perm-001", resource: "Organization", actions: ["manage", "view"], description: "Organization-level settings and configuration", category: "Administration" },
    { id: "perm-002", resource: "Users", actions: ["manage", "invite", "deactivate", "view"], description: "User account management and provisioning", category: "Administration" },
    { id: "perm-003", resource: "Roles", actions: ["manage", "assign", "view"], description: "RBAC role definition and assignment", category: "Access Control" },
    { id: "perm-004", resource: "Groups", actions: ["manage", "assign", "sync", "view"], description: "GBAC group management and directory sync", category: "Access Control" },
    { id: "perm-005", resource: "Sessions", actions: ["view", "respond", "terminate"], description: "Agent session monitoring and interaction", category: "Operations" },
    { id: "perm-006", resource: "Prompts", actions: ["view", "respond", "escalate"], description: "Decision prompt handling and escalation", category: "Operations" },
    { id: "perm-007", resource: "Traces", actions: ["view", "export"], description: "Decision trace and hash chain access", category: "Observability" },
    { id: "perm-008", resource: "Audit", actions: ["view", "export", "configure"], description: "Audit log access and retention settings", category: "Compliance" },
    { id: "perm-009", resource: "Integrity", actions: ["verify", "view"], description: "System integrity verification and monitoring", category: "Security" },
    { id: "perm-010", resource: "Policies", actions: ["manage", "view", "override"], description: "Governance policy configuration and overrides", category: "Governance" },
    { id: "perm-011", resource: "Escalations", actions: ["review", "override", "configure"], description: "Escalation routing, review, and threshold configuration", category: "Governance" },
    { id: "perm-012", resource: "Compliance", actions: ["view", "configure", "export"], description: "Compliance framework configuration and reporting", category: "Compliance" },
    { id: "perm-013", resource: "API Keys", actions: ["manage", "rotate", "revoke", "view"], description: "API key lifecycle management", category: "Security" },
    { id: "perm-014", resource: "Notifications", actions: ["manage", "view", "test"], description: "Alert and notification channel configuration", category: "Operations" },
    { id: "perm-015", resource: "Settings", actions: ["view", "manage"], description: "System-level settings and diagnostics", category: "Administration" },
  ],
  sso: {
    provider: "saml",
    enabled: true,
    entityId: "https://atlasbridge.local/saml/metadata",
    ssoUrl: "https://idp.atlasbridge.local/sso/saml",
    certificate: "[REDACTED:x509-certificate]",
    autoProvision: true,
    defaultRole: "Viewer",
    allowedDomains: ["atlasbridge.local", "atlasbridge.corp"],
    jitProvisioning: true,
    forceAuth: false,
    sessionDuration: 480,
  },
  compliance: {
    frameworks: ["SOC2", "ISO27001", "GDPR"],
    auditRetentionDays: 730,
    traceRetentionDays: 365,
    sessionRetentionDays: 180,
    dataResidency: "EU-West (Frankfurt)",
    encryptionAtRest: true,
    encryptionInTransit: true,
    autoRedaction: true,
    dlpEnabled: true,
    lastAuditDate: new Date(Date.now() - 45 * 86400000).toISOString(),
    nextAuditDate: new Date(Date.now() + 45 * 86400000).toISOString(),
  },
  sessionPolicy: {
    maxConcurrentSessions: 20,
    sessionTimeoutMinutes: 120,
    inactivityTimeoutMinutes: 30,
    autoTerminateOnEscalation: false,
    requireApprovalAboveRisk: "high",
    maxEscalationsPerSession: 10,
    recordAllSessions: true,
    allowedTools: ["GitHub Actions", "Terraform", "Docker Compose", "kubectl", "AWS CLI", "Ansible", "Helm", "Pulumi", "CloudFormation", "GCP CLI"],
    blockedTools: ["rm -rf", "format", "fdisk"],
    riskAutoEscalationThreshold: 0.7,
  },
};

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  await seedDatabase();

  const LOOPBACK = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);
  const wss = new WebSocketServer({ server: httpServer, path: "/ws/terminal" });
  wss.on("connection", (ws: WebSocket, req) => {
    const ip = req.socket.remoteAddress ?? "";
    if (!LOOPBACK.has(ip)) {
      ws.close(1008, "Terminal access is restricted to loopback connections.");
      return;
    }
    handleTerminalConnection(ws);
  });

  // -----------------------------------------------------------------------
  // Version check endpoint
  // -----------------------------------------------------------------------

  app.get("/api/version", async (_req, res) => {
    const current = repo.getSettings().version;
    try {
      const response = await fetch("https://pypi.org/pypi/atlasbridge/json", {
        signal: AbortSignal.timeout(5000),
      });
      const data = await response.json() as { info: { version: string } };
      const latest = data.info.version;
      res.json({
        current,
        latest,
        updateAvailable: latest !== current,
        upgradeCommand: "pip install --upgrade atlasbridge",
      });
    } catch {
      res.json({ current, latest: null, updateAvailable: false, upgradeCommand: "pip install --upgrade atlasbridge" });
    }
  });

  // -----------------------------------------------------------------------
  // Operational endpoints — read from AtlasBridge DB via repo
  // -----------------------------------------------------------------------

  app.get("/api/overview", (_req, res) => {
    res.json(repo.getOverview());
  });

  app.get("/api/sessions", (_req, res) => {
    res.json(repo.listSessions());
  });

  app.get("/api/sessions/:id", (req, res) => {
    const detail = repo.getSession(req.params.id);
    if (!detail) {
      res.status(404).json({ error: "Session not found" });
      return;
    }
    res.json(detail);
  });

  app.get("/api/prompts", (_req, res) => {
    res.json(repo.listPrompts());
  });

  app.get("/api/traces", (_req, res) => {
    res.json(repo.listTraces());
  });

  app.get("/api/integrity", (_req, res) => {
    res.json(repo.getIntegrity());
  });

  app.get("/api/audit", (_req, res) => {
    res.json(repo.listAuditEvents());
  });

  app.get("/api/settings", (_req, res) => {
    res.json(repo.getSettings());
  });

  // -----------------------------------------------------------------------
  // Organization settings — dashboard DB (RBAC, CRUD)
  // -----------------------------------------------------------------------

  app.get("/api/settings/organization", async (_req, res) => {
    try {
      const [dbUsers, dbGroups, dbRoles, dbApiKeys, dbPolicies, dbNotifications, dbIpAllowlist, dbPermissions] = await Promise.all([
        storage.getUsers(),
        storage.getGroups(),
        storage.getRoles(),
        storage.getApiKeys(),
        storage.getSecurityPolicies(),
        storage.getNotifications(),
        storage.getIpAllowlist(),
        storage.getRbacPermissions(),
      ]);
      const permissions = dbPermissions.length > 0
        ? dbPermissions.map(p => ({ id: p.externalId, resource: p.resource, actions: p.actions, description: p.description, category: p.category }))
        : orgSettingsStatic.permissions;
      res.json({
        ...orgSettingsStatic,
        permissions,
        users: dbUsers,
        groups: dbGroups,
        roles: dbRoles,
        apiKeys: dbApiKeys,
        securityPolicies: dbPolicies,
        notifications: dbNotifications,
        ipAllowlist: dbIpAllowlist,
      });
    } catch (e) {
      console.error("Failed to load org settings:", e);
      res.status(500).json({ error: "Failed to load organization settings" });
    }
  });

  // Permission matrix CRUD
  app.post("/api/permissions", requireCsrf, operatorRateLimiter, async (req, res) => {
    try {
      const body = req.body;
      const perm = await storage.createRbacPermission({
        externalId: `perm-${Date.now()}`,
        resource: body.resource,
        actions: body.actions || [],
        description: body.description || "",
        category: body.category || "",
      });
      res.status(201).json({ id: perm.externalId, resource: perm.resource, actions: perm.actions, description: perm.description, category: perm.category });
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to create permission" });
    }
  });

  app.patch("/api/permissions/:externalId", requireCsrf, operatorRateLimiter, async (req, res) => {
    try {
      const externalId = String(req.params.externalId);
      const body = req.body;
      // Look up by externalId to get integer id
      const all = await storage.getRbacPermissions();
      const existing = all.find(p => p.externalId === externalId);
      if (!existing) { res.status(404).json({ error: "Permission not found" }); return; }
      const perm = await storage.updateRbacPermission(existing.id, {
        resource: body.resource,
        actions: body.actions,
        description: body.description,
        category: body.category,
      });
      if (!perm) { res.status(404).json({ error: "Permission not found" }); return; }
      res.json({ id: perm.externalId, resource: perm.resource, actions: perm.actions, description: perm.description, category: perm.category });
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to update permission" });
    }
  });

  app.delete("/api/permissions/:externalId", requireCsrf, operatorRateLimiter, async (req, res) => {
    try {
      const externalId = String(req.params.externalId);
      const all = await storage.getRbacPermissions();
      const existing = all.find(p => p.externalId === externalId);
      if (!existing) { res.status(404).json({ error: "Permission not found" }); return; }
      await storage.deleteRbacPermission(existing.id);
      res.json({ ok: true });
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to delete permission" });
    }
  });

  app.post("/api/users", async (req, res) => {
    try {
      const body = req.body;
      const user = await storage.createUser({
        externalId: `usr-${Date.now()}`,
        username: body.username,
        email: body.email,
        displayName: body.displayName,
        role: body.role || "Viewer",
        status: "pending",
        mfaStatus: "disabled",
        groups: body.groups || [],
        loginMethod: body.loginMethod || "Invite Pending",
      });
      res.status(201).json(user);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to create user" });
    }
  });

  app.patch("/api/users/:id", async (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const user = await storage.updateUser(id, req.body);
      if (!user) { res.status(404).json({ error: "User not found" }); return; }
      res.json(user);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to update user" });
    }
  });

  app.delete("/api/users/:id", async (req, res) => {
    const id = parseInt(req.params.id);
    const deleted = await storage.deleteUser(id);
    if (!deleted) { res.status(404).json({ error: "User not found" }); return; }
    res.status(204).end();
  });

  app.post("/api/groups", async (req, res) => {
    try {
      const body = req.body;
      const group = await storage.createGroup({
        externalId: `grp-${Date.now()}`,
        name: body.name,
        description: body.description || "",
        memberCount: 0,
        roles: body.roles || [],
        permissionLevel: body.permissionLevel || "read",
        syncSource: "Manual",
      });
      res.status(201).json(group);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to create group" });
    }
  });

  app.patch("/api/groups/:id", async (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const group = await storage.updateGroup(id, req.body);
      if (!group) { res.status(404).json({ error: "Group not found" }); return; }
      res.json(group);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to update group" });
    }
  });

  app.delete("/api/groups/:id", async (req, res) => {
    const id = parseInt(req.params.id);
    const deleted = await storage.deleteGroup(id);
    if (!deleted) { res.status(404).json({ error: "Group not found" }); return; }
    res.status(204).end();
  });

  app.post("/api/roles", async (req, res) => {
    try {
      const body = req.body;
      const role = await storage.createRole({
        externalId: `role-${Date.now()}`,
        name: body.name,
        description: body.description || "",
        permissions: body.permissions || [],
        isSystem: false,
        memberCount: 0,
      });
      res.status(201).json(role);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to create role" });
    }
  });

  app.patch("/api/roles/:id", async (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const role = await storage.updateRole(id, req.body);
      if (!role) { res.status(404).json({ error: "Role not found" }); return; }
      res.json(role);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to update role" });
    }
  });

  app.delete("/api/roles/:id", async (req, res) => {
    const id = parseInt(req.params.id);
    const deleted = await storage.deleteRole(id);
    if (!deleted) { res.status(404).json({ error: "Role not found" }); return; }
    res.status(204).end();
  });

  app.post("/api/api-keys", async (req, res) => {
    try {
      const body = req.body;
      const prefix = `ab_${body.name?.toLowerCase().replace(/\s+/g, "_").slice(0, 8)}_`;
      const key = await storage.createApiKey({
        externalId: `key-${Date.now()}`,
        name: body.name,
        prefix,
        scopes: body.scopes || [],
        status: "active",
        createdBy: body.createdBy || "admin",
        expiresAt: body.expiresAt ? new Date(body.expiresAt).toISOString() : new Date(Date.now() + 90 * 86400000).toISOString(),
        rateLimit: body.rateLimit || 100,
      });
      res.status(201).json(key);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to create API key" });
    }
  });

  app.patch("/api/api-keys/:id", async (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const key = await storage.updateApiKey(id, req.body);
      if (!key) { res.status(404).json({ error: "API key not found" }); return; }
      res.json(key);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to update API key" });
    }
  });

  app.delete("/api/api-keys/:id", async (req, res) => {
    const id = parseInt(req.params.id);
    const deleted = await storage.deleteApiKey(id);
    if (!deleted) { res.status(404).json({ error: "API key not found" }); return; }
    res.status(204).end();
  });

  app.post("/api/api-keys/:id/rotate", requireCsrf, operatorRateLimiter, async (req, res) => {
    try {
      const id = parseInt(String(req.params.id));
      const newExtId = `sk_${randomUUID().replace(/-/g, "").slice(0, 24)}`;
      const newPrefix = newExtId.slice(0, 10);
      const updated = await storage.updateApiKey(id, { externalId: newExtId, prefix: newPrefix });
      if (!updated) { res.status(404).json({ error: "API key not found" }); return; }
      insertOperatorAuditLog({ method: "POST", path: `/api/api-keys/${id}/rotate`, action: `apikey-rotate:${id}`, body: {}, result: "ok" });
      res.json({ ok: true, newKey: newExtId, prefix: newPrefix });
    } catch (e: any) {
      res.status(500).json({ error: e.message || "Failed to rotate API key" });
    }
  });

  app.patch("/api/security-policies/:id", async (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const policy = await storage.updateSecurityPolicy(id, req.body);
      if (!policy) { res.status(404).json({ error: "Policy not found" }); return; }
      res.json(policy);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to update policy" });
    }
  });

  app.post("/api/notifications", async (req, res) => {
    try {
      const body = req.body;
      const notif = await storage.createNotification({
        externalId: `notif-${Date.now()}`,
        channel: body.channel,
        name: body.name,
        enabled: body.enabled ?? true,
        destination: body.destination,
        events: body.events || [],
        minSeverity: body.minSeverity || "info",
      });
      res.status(201).json(notif);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to create notification" });
    }
  });

  app.patch("/api/notifications/:id", async (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const notif = await storage.updateNotification(id, req.body);
      if (!notif) { res.status(404).json({ error: "Notification not found" }); return; }
      res.json(notif);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to update notification" });
    }
  });

  app.delete("/api/notifications/:id", async (req, res) => {
    const id = parseInt(req.params.id);
    const deleted = await storage.deleteNotification(id);
    if (!deleted) { res.status(404).json({ error: "Notification not found" }); return; }
    res.status(204).end();
  });

  app.post("/api/ip-allowlist", async (req, res) => {
    try {
      const body = req.body;
      const entry = await storage.createIpAllowlistEntry({
        externalId: `ip-${Date.now()}`,
        cidr: body.cidr,
        label: body.label,
        addedBy: body.addedBy || "admin",
      });
      res.status(201).json(entry);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to add IP entry" });
    }
  });

  app.delete("/api/ip-allowlist/:id", async (req, res) => {
    const id = parseInt(req.params.id);
    const deleted = await storage.deleteIpAllowlistEntry(id);
    if (!deleted) { res.status(404).json({ error: "IP entry not found" }); return; }
    res.status(204).end();
  });

  // -----------------------------------------------------------------------
  // Repository connections + compliance scanning (dashboard DB)
  // -----------------------------------------------------------------------

  app.get("/api/repo-connections", async (_req, res) => {
    try {
      const repos = await storage.getRepoConnections();
      res.json(repos);
    } catch (e) {
      res.status(500).json({ error: "Failed to load repo connections" });
    }
  });

  app.post("/api/repo-connections", async (req, res) => {
    try {
      const body = req.body;
      const repoConn = await storage.createRepoConnection({
        provider: body.provider,
        owner: body.owner,
        repo: body.repo,
        branch: body.branch || "main",
        url: body.url,
        status: "connected",
        accessToken: body.accessToken,
        connectedBy: body.connectedBy || "admin",
        complianceLevel: body.complianceLevel || "standard",
      });
      res.status(201).json(repoConn);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to connect repository" });
    }
  });

  app.patch("/api/repo-connections/:id", async (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const repoConn = await storage.updateRepoConnection(id, req.body);
      if (!repoConn) { res.status(404).json({ error: "Repository not found" }); return; }
      res.json(repoConn);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to update repository" });
    }
  });

  app.delete("/api/repo-connections/:id", async (req, res) => {
    const id = parseInt(req.params.id);
    const deleted = await storage.deleteRepoConnection(id);
    if (!deleted) { res.status(404).json({ error: "Repository not found" }); return; }
    res.status(204).end();
  });

  app.post("/api/repo-connections/:id/scan", async (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const repoConn = await storage.getRepoConnection(id);
      if (!repoConn) { res.status(404).json({ error: "Repository not found" }); return; }

      const level = (req.body.complianceLevel || repoConn.complianceLevel || "standard") as string;
      const result = runComplianceScan(
        { provider: repoConn.provider, owner: repoConn.owner, repo: repoConn.repo, branch: repoConn.branch },
        level
      );

      await storage.updateRepoConnection(id, {
        complianceScore: result.overallScore,
        complianceLevel: level,
        lastSynced: new Date().toISOString(),
      });

      await storage.createComplianceScan({
        repoConnectionId: id,
        complianceLevel: level,
        overallScore: result.overallScore,
        categories: result.categories,
        suggestions: result.suggestions,
      });

      res.json(result);
    } catch (e: any) {
      res.status(400).json({ error: e.message || "Failed to run compliance scan" });
    }
  });

  app.get("/api/repo-connections/:id/scans", async (req, res) => {
    try {
      const id = parseInt(req.params.id);
      const scans = await storage.getComplianceScans(id);
      res.json(scans);
    } catch (e) {
      res.status(500).json({ error: "Failed to load compliance scans" });
    }
  });

  // -----------------------------------------------------------------------
  // Evidence engine endpoints
  // -----------------------------------------------------------------------

  app.get("/api/evidence/score", (req, res) => {
    const sessionId = req.query.sessionId as string | undefined;
    res.json(computeGovernanceScore(sessionId || undefined));
  });

  app.get("/api/evidence/export/json", (req, res) => {
    const sessionId = req.query.sessionId as string | undefined;
    const bundle = generateEvidenceJSON(sessionId || undefined);
    res.json(bundle);
  });

  app.get("/api/evidence/export/csv", (req, res) => {
    const sessionId = req.query.sessionId as string | undefined;
    const csv = generateEvidenceCSV(sessionId || undefined);
    res.setHeader("Content-Type", "text/csv");
    res.setHeader("Content-Disposition", `attachment; filename="decisions-${Date.now()}.csv"`);
    res.send(csv);
  });

  app.get("/api/evidence/export/bundle", (req, res) => {
    const sessionId = req.query.sessionId as string | undefined;
    const bundle = generateFullBundle(sessionId || undefined);
    const entry = addGeneratedBundle({
      generatedAt: bundle.evidence.generatedAt,
      sessionId: sessionId || undefined,
      format: "bundle",
      decisionCount: bundle.evidence.decisions.length,
      escalationCount: bundle.evidence.escalations.length,
      integrityStatus: bundle.integrityReport.overallStatus,
      governanceScore: bundle.evidence.governanceScore.overall,
      manifestHash: bundle.manifest.files.map(f => f.sha256).join(",").slice(0, 16),
    });
    res.json({ ...bundle, bundleId: entry.id });
  });

  app.get("/api/evidence/bundles", (_req, res) => {
    res.json(listGeneratedBundles());
  });

  app.get("/api/evidence/packs", (_req, res) => {
    res.json(compliancePacks);
  });

  app.get("/api/evidence/integrity", (_req, res) => {
    const bundle = generateEvidenceJSON();
    res.json(bundle.integrityReport);
  });

  // ---------------------------------------------------------------------------
  // Workspace trust — read and manage per-workspace consent
  // ---------------------------------------------------------------------------

  app.get("/api/workspaces", async (_req, res) => {
    try {
      const { runAtlasBridge } = await import("./routes/operator");
      const { stdout } = await runAtlasBridge(["workspace", "list", "--json"]);
      const data = JSON.parse(stdout.trim() || "[]");
      res.json(data);
    } catch {
      res.json([]);
    }
  });

  app.post(
    "/api/workspaces/trust",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const body = req.body as Record<string, unknown>;
      const path = typeof body.path === "string" ? body.path : "";
      if (!path) {
        res.status(400).json({ error: "path is required" });
        return;
      }
      try {
        const { stdout } = await runAtlasBridge(["workspace", "trust", path]);
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/workspaces/trust",
          action: `workspace-trust:${path}`,
          body: { path },
          result: "ok",
        });
        res.json({ ok: true, path, detail: stdout.trim() });
      } catch (err: any) {
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/workspaces/trust",
          action: `workspace-trust:${path}`,
          body: { path },
          result: "error",
          error: err.message,
        });
        res.status(503).json({ error: "Failed to grant workspace trust", detail: err.message });
      }
    },
  );

  app.delete(
    "/api/workspaces/trust",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const body = req.body as Record<string, unknown>;
      const path = typeof body.path === "string" ? body.path : "";
      if (!path) {
        res.status(400).json({ error: "path is required" });
        return;
      }
      try {
        const { stdout } = await runAtlasBridge(["workspace", "revoke", path]);
        insertOperatorAuditLog({
          method: "DELETE",
          path: "/api/workspaces/trust",
          action: `workspace-revoke:${path}`,
          body: { path },
          result: "ok",
        });
        res.json({ ok: true, path, detail: stdout.trim() });
      } catch (err: any) {
        insertOperatorAuditLog({
          method: "DELETE",
          path: "/api/workspaces/trust",
          action: `workspace-revoke:${path}`,
          body: { path },
          result: "error",
          error: err.message,
        });
        res.status(503).json({ error: "Failed to revoke workspace trust", detail: err.message });
      }
    },
  );

  // ---------------------------------------------------------------------------
  // Providers — AI provider key management (metadata only; keys stay in keychain)
  // ---------------------------------------------------------------------------

  app.get("/api/providers", async (_req, res) => {
    try {
      const { runAtlasBridge } = await import("./routes/operator");
      const { stdout } = await runAtlasBridge(["providers", "list", "--json"]);
      const data = JSON.parse(stdout.trim() || "[]");
      res.json(data);
    } catch {
      res.json([]);
    }
  });

  app.post(
    "/api/providers",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const body = req.body as Record<string, unknown>;
      const provider = typeof body.provider === "string" ? body.provider : "";
      const key = typeof body.key === "string" ? body.key : "";
      if (!provider || !key) {
        res.status(400).json({ error: "provider and key are required" });
        return;
      }
      try {
        await runAtlasBridge(["providers", "add", provider, key]);
        // DO NOT include key in audit log — redact it
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/providers",
          action: `provider-add:${provider}`,
          body: { provider, key: "[REDACTED]" },
          result: "ok",
        });
        res.json({ ok: true, provider });
      } catch (err: any) {
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/providers",
          action: `provider-add:${provider}`,
          body: { provider, key: "[REDACTED]" },
          result: "error",
          error: err.message,
        });
        res.status(503).json({ error: "Failed to store provider key", detail: err.message });
      }
    },
  );

  app.post(
    "/api/providers/:name/validate",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const name = String(req.params.name);
      try {
        const { stdout } = await runAtlasBridge(["providers", "validate", name]);
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/providers/${name}/validate`,
          action: `provider-validate:${name}`,
          body: {},
          result: "ok",
        });
        res.json({ ok: true, provider: name, detail: stdout.trim() });
      } catch (err: any) {
        const detail = (err.stderr as string | undefined)?.trim() || err.message;
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/providers/${name}/validate`,
          action: `provider-validate:${name}`,
          body: {},
          result: "error",
          error: err.message,
        });
        res.status(422).json({ ok: false, provider: name, error: "Validation failed", detail });
      }
    },
  );

  app.delete(
    "/api/providers/:name",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const name = String(req.params.name);
      try {
        await runAtlasBridge(["providers", "remove", name]);
        insertOperatorAuditLog({
          method: "DELETE",
          path: `/api/providers/${name}`,
          action: `provider-remove:${name}`,
          body: {},
          result: "ok",
        });
        res.json({ ok: true, provider: name });
      } catch (err: any) {
        res.status(503).json({ error: "Failed to remove provider", detail: err.message });
      }
    },
  );

  // ---------------------------------------------------------------------------
  // Channel configuration
  // ---------------------------------------------------------------------------

  app.get("/api/channels", (_req, res) => {
    const cfg = readAtlasBridgeConfig();
    const tg = cfg.telegram as Record<string, unknown> | undefined;
    const sl = cfg.slack as Record<string, unknown> | undefined;
    res.json({
      telegram: tg ? { configured: true, users: tg.allowed_users } : null,
      slack: sl ? { configured: true, users: sl.allowed_users } : null,
    });
  });

  app.post(
    "/api/channels/telegram",
    requireCsrf,
    operatorRateLimiter,
    (req, res) => {
      const { token, users } = req.body as { token?: string; users?: string };
      if (!token || !users) {
        res.status(400).json({ error: "token and users are required" });
        return;
      }
      try {
        const cfg = readAtlasBridgeConfig();
        const userIds = String(users).split(",").map(u => {
          const n = parseInt(u.trim(), 10);
          return isNaN(n) ? u.trim() : n;
        });
        cfg.telegram = { bot_token: token, allowed_users: userIds };
        writeAtlasBridgeConfig(cfg);
        res.json({ ok: true });
      } catch (err: any) {
        res.status(500).json({ error: "Failed to configure Telegram channel", detail: err.message });
      }
    },
  );

  app.post(
    "/api/channels/slack",
    requireCsrf,
    operatorRateLimiter,
    (req, res) => {
      const { token, appToken, users } = req.body as { token?: string; appToken?: string; users?: string };
      if (!token || !appToken || !users) {
        res.status(400).json({ error: "token, appToken, and users are required" });
        return;
      }
      try {
        const cfg = readAtlasBridgeConfig();
        const userIds = String(users).split(",").map(u => u.trim()).filter(Boolean);
        cfg.slack = { bot_token: token, app_token: appToken, allowed_users: userIds };
        writeAtlasBridgeConfig(cfg);
        res.json({ ok: true });
      } catch (err: any) {
        res.status(500).json({ error: "Failed to configure Slack channel", detail: err.message });
      }
    },
  );

  app.delete(
    "/api/channels/:name",
    requireCsrf,
    operatorRateLimiter,
    (req, res) => {
      const name = String(req.params.name);
      if (!["telegram", "slack"].includes(name)) {
        res.status(400).json({ error: "Invalid channel name" });
        return;
      }
      try {
        const cfg = readAtlasBridgeConfig();
        delete cfg[name];
        writeAtlasBridgeConfig(cfg);
        res.json({ ok: true });
      } catch (err: any) {
        res.status(500).json({ error: "Failed to remove channel", detail: err.message });
      }
    },
  );

  // ---------------------------------------------------------------------------
  // Session start / stop from dashboard
  // ---------------------------------------------------------------------------

  const VALID_ADAPTERS = new Set(["claude", "openai", "gemini", "claude-code", "custom"]);
  const VALID_SESSION_MODES = new Set(["off", "assist", "full"]);

  app.post(
    "/api/sessions/start",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const body = req.body as Record<string, unknown>;
      const adapter = typeof body.adapter === "string" ? body.adapter.toLowerCase() : "claude";
      const mode = typeof body.mode === "string" ? body.mode.toLowerCase() : "off";
      const cwd = typeof body.cwd === "string" ? body.cwd : "";
      const profile = typeof body.profile === "string" ? body.profile : "";
      const label = typeof body.label === "string" ? body.label : "";
      const customCommand = typeof body.customCommand === "string" ? body.customCommand.trim() : "";

      if (!VALID_ADAPTERS.has(adapter)) {
        res.status(400).json({ error: `Invalid adapter. Choose from: ${Array.from(VALID_ADAPTERS).join(", ")}` });
        return;
      }
      if (adapter === "custom" && !customCommand) {
        res.status(400).json({ error: "A command is required when using the custom adapter." });
        return;
      }
      if (!VALID_SESSION_MODES.has(mode)) {
        res.status(400).json({ error: "Invalid mode. Must be: off, assist, full" });
        return;
      }

      ensureAutopilotReady();

      // Prevent duplicate session starts from rapid double-clicks.
      if ((globalThis as any).__lastSessionStart &&
          Date.now() - (globalThis as any).__lastSessionStart < 3000) {
        res.status(429).json({ error: "Session start already in progress. Please wait." });
        return;
      }
      (globalThis as any).__lastSessionStart = Date.now();

      const args = ["sessions", "start", "--adapter", adapter, "--mode", mode, "--json"];
      if (customCommand) args.push("--custom-command", customCommand);
      if (cwd) args.push("--cwd", cwd);
      if (profile) args.push("--profile", profile);
      if (label) args.push("--label", label);

      try {
        const { stdout } = await runAtlasBridge(args);
        const parsed = JSON.parse(stdout.trim() || "{}");
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/sessions/start",
          action: `session-start:${adapter}:${mode}`,
          body: { adapter, mode, cwd: cwd || undefined, profile: profile || undefined },
          result: "ok",
        });
        res.json({ ok: true, ...parsed });
      } catch (err: any) {
        const detail = (err.stderr as string | undefined)?.trim() || err.message;
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/sessions/start",
          action: `session-start:${adapter}:${mode}`,
          body: { adapter, mode },
          result: "error",
          error: err.message,
        });
        res.status(503).json({ error: "Failed to start session", detail });
      }
    },
  );

  app.post(
    "/api/sessions/:id/stop",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const sessionId = String(req.params.id);
      try {
        const { stdout } = await runAtlasBridge(["sessions", "stop", sessionId, "--json"]);
        const parsed = JSON.parse(stdout.trim() || "{}");
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/sessions/${sessionId}/stop`,
          action: `session-stop:${sessionId}`,
          body: {},
          result: "ok",
        });
        res.json({ ok: true, session_id: sessionId, ...parsed });
      } catch (err: any) {
        const detail =
          (err.stderr as string | undefined)?.trim() ||
          (err.stdout as string | undefined)?.trim() ||
          err.message;
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/sessions/${sessionId}/stop`,
          action: `session-stop:${sessionId}`,
          body: {},
          result: "error",
          error: err.message,
        });
        res.status(503).json({ error: "Failed to stop session", detail });
      }
    },
  );

  // ---------------------------------------------------------------------------
  // Session pause / resume
  // ---------------------------------------------------------------------------

  app.post(
    "/api/sessions/:id/pause",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const sessionId = String(req.params.id);
      try {
        const { stdout } = await runAtlasBridge(["sessions", "pause", sessionId, "--json"]);
        const parsed = JSON.parse(stdout.trim() || "{}");
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/sessions/${sessionId}/pause`,
          action: `session-pause:${sessionId}`,
          body: {},
          result: "ok",
        });
        res.json({ ok: true, session_id: sessionId, ...parsed });
      } catch (err: any) {
        const detail =
          (err.stderr as string | undefined)?.trim() ||
          (err.stdout as string | undefined)?.trim() ||
          err.message;
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/sessions/${sessionId}/pause`,
          action: `session-pause:${sessionId}`,
          body: {},
          result: "error",
          error: err.message,
        });
        res.status(503).json({ error: "Failed to pause session", detail });
      }
    },
  );

  app.post(
    "/api/sessions/:id/resume",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const sessionId = String(req.params.id);
      try {
        const { stdout } = await runAtlasBridge(["sessions", "resume", sessionId, "--json"]);
        const parsed = JSON.parse(stdout.trim() || "{}");
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/sessions/${sessionId}/resume`,
          action: `session-resume:${sessionId}`,
          body: {},
          result: "ok",
        });
        res.json({ ok: true, session_id: sessionId, ...parsed });
      } catch (err: any) {
        const detail =
          (err.stderr as string | undefined)?.trim() ||
          (err.stdout as string | undefined)?.trim() ||
          err.message;
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/sessions/${sessionId}/resume`,
          action: `session-resume:${sessionId}`,
          body: {},
          result: "error",
          error: err.message,
        });
        res.status(503).json({ error: "Failed to resume session", detail });
      }
    },
  );

  // ---------------------------------------------------------------------------
  // Chat panel — pending prompt relay
  // ---------------------------------------------------------------------------

  app.get("/api/chat/prompts", async (req, res) => {
    const sessionId = String(req.query.session_id ?? "");
    const prompts = repo.getPendingPrompts(sessionId);
    res.json(prompts);
  });

  app.post(
    "/api/chat/reply",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const { session_id, prompt_id, value } = req.body as {
        session_id?: string;
        prompt_id?: string;
        value?: string;
      };
      if (!session_id || !prompt_id || !value) {
        res.status(400).json({ error: "session_id, prompt_id, and value are required" });
        return;
      }
      try {
        const { stdout } = await runAtlasBridge([
          "sessions",
          "reply",
          session_id,
          prompt_id,
          value,
        ]);
        const parsed = JSON.parse(stdout.trim() || "{}");
        if (parsed.ok === false) {
          res.status(422).json({ error: parsed.error || "Reply failed" });
          return;
        }
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/chat/reply",
          action: `chat-reply:${session_id}:${prompt_id}`,
          body: { session_id, prompt_id },
          result: "ok",
        });
        res.json({ ok: true });
      } catch (err: any) {
        const detail = (err.stderr as string | undefined)?.trim() || err.message;
        res.status(503).json({ error: "Failed to inject reply", detail });
      }
    },
  );

  // ---------------------------------------------------------------------------
  // Expert Agent endpoints
  // ---------------------------------------------------------------------------

  const VALID_AGENT_PROVIDERS = new Set(["anthropic", "openai", "google"]);

  app.post(
    "/api/agent/start",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const body = req.body as Record<string, unknown>;
      const provider = typeof body.provider === "string" ? body.provider.toLowerCase() : "";
      const model = typeof body.model === "string" ? body.model : "";

      if (provider && !VALID_AGENT_PROVIDERS.has(provider)) {
        res.status(400).json({ error: `Invalid provider. Choose from: ${Array.from(VALID_AGENT_PROVIDERS).join(", ")}` });
        return;
      }

      // Prevent duplicate agent starts from rapid double-clicks.
      if ((globalThis as any).__lastAgentStart &&
          Date.now() - (globalThis as any).__lastAgentStart < 3000) {
        res.status(429).json({ error: "Agent start already in progress. Please wait." });
        return;
      }
      (globalThis as any).__lastAgentStart = Date.now();

      const args = ["agent", "start", "--background", "--json"];
      if (provider) args.push("--provider", provider);
      if (model) args.push("--model", model);

      try {
        const { stdout } = await runAtlasBridge(args);
        const parsed = JSON.parse(stdout.trim() || "{}");
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/agent/start",
          action: `agent-start:${provider || "default"}`,
          body: { provider: provider || "default", model: model || "default" },
          result: "ok",
        });
        res.json({ ok: true, ...parsed });
      } catch (err: any) {
        // CLI writes JSON errors to stdout, not stderr
        let detail = "";
        const out = (err.stdout as string | undefined)?.trim();
        if (out) {
          try {
            const parsed = JSON.parse(out);
            detail = parsed.error || out;
          } catch {
            detail = out;
          }
        }
        if (!detail) detail = (err.stderr as string | undefined)?.trim() || err.message;
        insertOperatorAuditLog({
          method: "POST",
          path: "/api/agent/start",
          action: `agent-start:${provider || "default"}`,
          body: { provider, model },
          result: "error",
          error: detail,
        });
        res.status(503).json({ error: detail });
      }
    },
  );

  app.get("/api/agent/sessions/:id/turns", (_req, res) => {
    const turns = repo.listAgentTurns(_req.params.id);
    res.json(turns);
  });

  app.get("/api/agent/sessions/:id/state", (_req, res) => {
    const state = repo.getAgentState(_req.params.id);
    if (!state) {
      res.status(404).json({ error: "Session not found" });
      return;
    }
    res.json(state);
  });

  app.get("/api/agent/sessions/:id/plans", (_req, res) => {
    const plans = repo.listAgentPlans(_req.params.id);
    res.json(plans);
  });

  app.get("/api/agent/sessions/:id/decisions", (_req, res) => {
    const decisions = repo.listAgentDecisions(_req.params.id);
    res.json(decisions);
  });

  app.get("/api/agent/sessions/:id/tool-runs", (_req, res) => {
    const runs = repo.listAgentToolRuns(_req.params.id);
    res.json(runs);
  });

  app.get("/api/agent/sessions/:id/outcomes", (_req, res) => {
    const outcomes = repo.listAgentOutcomes(_req.params.id);
    res.json(outcomes);
  });

  app.post(
    "/api/agent/sessions/:id/message",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const sessionId = String(req.params.id);
      const body = req.body || {};
      const text = typeof body.text === "string" ? body.text : (typeof body.content === "string" ? body.content : "");
      if (!text) {
        res.status(400).json({ error: "text is required" });
        return;
      }
      try {
        const { stdout } = await runAtlasBridge([
          "agent", "message", sessionId, text, "--json",
        ]);
        const parsed = JSON.parse(stdout.trim() || "{}");
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/agent/sessions/${sessionId}/message`,
          action: `agent-message:${sessionId}`,
          body: { text: text.substring(0, 100) },
          result: "ok",
        });
        res.json(parsed);
      } catch (err: any) {
        const detail = (err.stderr as string | undefined)?.trim() || err.message;
        res.status(503).json({ error: "Failed to send message", detail });
      }
    },
  );

  app.post(
    "/api/agent/sessions/:id/approve",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const sessionId = String(req.params.id);
      const { plan_id } = req.body || {};
      if (!plan_id) {
        res.status(400).json({ error: "plan_id is required" });
        return;
      }
      try {
        const { stdout } = await runAtlasBridge([
          "agent", "approve", sessionId, String(plan_id), "--json",
        ]);
        const parsed = JSON.parse(stdout.trim() || "{}");
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/agent/sessions/${sessionId}/approve`,
          action: `agent-approve:${sessionId}:${plan_id}`,
          body: { plan_id },
          result: "ok",
        });
        res.json(parsed);
      } catch (err: any) {
        const detail = (err.stderr as string | undefined)?.trim() || err.message;
        res.status(503).json({ error: "Failed to approve plan", detail });
      }
    },
  );

  app.post(
    "/api/agent/sessions/:id/deny",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { runAtlasBridge } = await import("./routes/operator");
      const sessionId = String(req.params.id);
      const { plan_id } = req.body || {};
      if (!plan_id) {
        res.status(400).json({ error: "plan_id is required" });
        return;
      }
      try {
        const { stdout } = await runAtlasBridge([
          "agent", "deny", sessionId, String(plan_id), "--json",
        ]);
        const parsed = JSON.parse(stdout.trim() || "{}");
        insertOperatorAuditLog({
          method: "POST",
          path: `/api/agent/sessions/${sessionId}/deny`,
          action: `agent-deny:${sessionId}:${plan_id}`,
          body: { plan_id },
          result: "ok",
        });
        res.json(parsed);
      } catch (err: any) {
        const detail = (err.stderr as string | undefined)?.trim() || err.message;
        res.status(503).json({ error: "Failed to deny plan", detail });
      }
    },
  );

  // SSE stream for real-time agent updates
  app.get("/api/agent/sessions/:id/stream", (_req, res) => {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.flushHeaders();

    let lastTurnCount = 0;
    let lastPlanCount = 0;
    let lastToolRunCount = 0;

    const interval = setInterval(() => {
      try {
        const turns = repo.listAgentTurns(_req.params.id);
        const plans = repo.listAgentPlans(_req.params.id);
        const toolRuns = repo.listAgentToolRuns(_req.params.id);
        const state = repo.getAgentState(_req.params.id);

        if (turns.length !== lastTurnCount) {
          lastTurnCount = turns.length;
          res.write(`event: turn_update\ndata: ${JSON.stringify(turns[turns.length - 1])}\n\n`);
        }
        if (plans.length !== lastPlanCount) {
          lastPlanCount = plans.length;
          res.write(`event: plan_update\ndata: ${JSON.stringify(plans[0])}\n\n`);
        }
        if (toolRuns.length !== lastToolRunCount) {
          lastToolRunCount = toolRuns.length;
          res.write(`event: tool_run\ndata: ${JSON.stringify(toolRuns[toolRuns.length - 1])}\n\n`);
        }
        if (state) {
          res.write(`event: state_change\ndata: ${JSON.stringify(state)}\n\n`);
        }
      } catch {
        // Ignore errors during polling
      }
    }, 500);

    _req.on("close", () => {
      clearInterval(interval);
    });
  });

  // Agent profiles (static for v1)
  app.get("/api/agents", (_req, res) => {
    res.json([
      {
        name: "atlasbridge_expert",
        version: "1.0.0",
        description: "AtlasBridge Expert Agent — governance operations specialist",
        capabilities: [
          "ab_list_sessions", "ab_get_session", "ab_list_prompts",
          "ab_get_audit_events", "ab_get_traces", "ab_check_integrity",
          "ab_get_config", "ab_get_policy", "ab_explain_decision", "ab_get_stats",
          "ab_validate_policy", "ab_test_policy", "ab_set_mode", "ab_kill_switch",
        ],
        risk_tier: "moderate",
        max_autonomy: "assist",
      },
    ]);
  });

  // ---------------------------------------------------------------------------
  // Operator write actions (kill switch, autonomy mode, audit log)
  // ---------------------------------------------------------------------------
  registerOperatorRoutes(app);

  return httpServer;
}
