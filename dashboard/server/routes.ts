import type { Express } from "express";
import { createServer, type Server } from "http";
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
      const [dbUsers, dbGroups, dbRoles, dbApiKeys, dbPolicies, dbNotifications, dbIpAllowlist] = await Promise.all([
        storage.getUsers(),
        storage.getGroups(),
        storage.getRoles(),
        storage.getApiKeys(),
        storage.getSecurityPolicies(),
        storage.getNotifications(),
        storage.getIpAllowlist(),
      ]);
      res.json({
        ...orgSettingsStatic,
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
        const detail = (err.stderr as string | undefined)?.trim() ?? err.message;
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

  app.get("/api/channels", async (_req, res) => {
    try {
      const { runAtlasBridge } = await import("./routes/operator");
      const { stdout } = await runAtlasBridge(["config", "show", "--json"]);
      const cfg = JSON.parse(stdout);
      res.json({
        telegram: cfg.telegram ?? null,
        slack: cfg.slack ?? null,
      });
    } catch (err: any) {
      res.status(503).json({ error: "Failed to read channel config", detail: err.message });
    }
  });

  app.post(
    "/api/channels/telegram",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { token, users } = req.body as { token?: string; users?: string };
      if (!token || !users) {
        res.status(400).json({ error: "token and users are required" });
        return;
      }
      try {
        const { runAtlasBridge } = await import("./routes/operator");
        await runAtlasBridge(["channel", "add", "telegram", "--token", token, "--users", String(users)]);
        res.json({ ok: true });
      } catch (err: any) {
        res.status(503).json({ error: "Failed to configure Telegram channel", detail: err.message });
      }
    },
  );

  app.post(
    "/api/channels/slack",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const { token, appToken, users } = req.body as { token?: string; appToken?: string; users?: string };
      if (!token || !appToken || !users) {
        res.status(400).json({ error: "token, appToken, and users are required" });
        return;
      }
      try {
        const { runAtlasBridge } = await import("./routes/operator");
        await runAtlasBridge(["channel", "add", "slack", "--token", token, "--app-token", appToken, "--users", String(users)]);
        res.json({ ok: true });
      } catch (err: any) {
        res.status(503).json({ error: "Failed to configure Slack channel", detail: err.message });
      }
    },
  );

  app.delete(
    "/api/channels/:name",
    requireCsrf,
    operatorRateLimiter,
    async (req, res) => {
      const name = req.params.name;
      if (!["telegram", "slack"].includes(name)) {
        res.status(400).json({ error: "Invalid channel name" });
        return;
      }
      try {
        const { runAtlasBridge } = await import("./routes/operator");
        await runAtlasBridge(["channel", "remove", name]);
        res.json({ ok: true });
      } catch (err: any) {
        res.status(503).json({ error: "Failed to remove channel", detail: err.message });
      }
    },
  );

  // ---------------------------------------------------------------------------
  // Session start / stop from dashboard
  // ---------------------------------------------------------------------------

  const VALID_ADAPTERS = new Set(["claude", "openai", "gemini", "claude-code"]);
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

      if (!VALID_ADAPTERS.has(adapter)) {
        res.status(400).json({ error: `Invalid adapter. Choose from: ${Array.from(VALID_ADAPTERS).join(", ")}` });
        return;
      }
      if (!VALID_SESSION_MODES.has(mode)) {
        res.status(400).json({ error: "Invalid mode. Must be: off, assist, full" });
        return;
      }

      const args = ["sessions", "start", "--adapter", adapter, "--mode", mode, "--json"];
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
        const detail = (err.stderr as string | undefined)?.trim() ?? err.message;
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
        const detail = (err.stderr as string | undefined)?.trim() ?? err.message;
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
  // Operator write actions (kill switch, autonomy mode, audit log)
  // ---------------------------------------------------------------------------
  registerOperatorRoutes(app);

  return httpServer;
}
