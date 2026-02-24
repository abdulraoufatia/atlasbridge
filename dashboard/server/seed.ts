import { db } from "./db";
import { users, groups, roles, apiKeys, securityPolicies, notifications, ipAllowlist } from "@shared/schema";

const now = new Date();
const isoNow = now.toISOString();
const h = (hoursAgo: number) => new Date(now.getTime() - hoursAgo * 3600000).toISOString();
const d = (daysAgo: number) => new Date(now.getTime() - daysAgo * 86400000).toISOString();
const m = (minsAgo: number) => new Date(now.getTime() - minsAgo * 60000).toISOString();
const futureD = (daysAhead: number) => new Date(now.getTime() + daysAhead * 86400000).toISOString();

export async function seedDatabase() {
  const existingUsers = await db.select().from(users).limit(1);
  if (existingUsers.length > 0) return;

  await db.insert(roles).values([
    { externalId: "role-001", name: "Super Admin", description: "Full unrestricted access to all resources, settings, and administrative functions", permissions: (["*"]), isSystem: true, memberCount: 2, createdAt: d(180) },
    { externalId: "role-002", name: "Org Admin", description: "Organization-level administration including user management, RBAC, and policy configuration", permissions: (["org.manage", "users.manage", "roles.manage", "groups.manage", "policies.manage", "sessions.view", "audit.view", "settings.view"]), isSystem: true, memberCount: 3, createdAt: d(180) },
    { externalId: "role-003", name: "Security Officer", description: "Security-focused role with access to audit logs, compliance settings, integrity checks, and escalation review", permissions: (["audit.view", "audit.export", "integrity.verify", "compliance.view", "escalations.review", "sessions.view", "traces.view", "policies.view"]), isSystem: true, memberCount: 2, createdAt: d(180) },
    { externalId: "role-004", name: "Operator", description: "Day-to-day operations including session monitoring, prompt response, and trace analysis", permissions: (["sessions.view", "sessions.respond", "prompts.view", "prompts.respond", "traces.view", "overview.view"]), isSystem: false, memberCount: 8, createdAt: d(120) },
    { externalId: "role-005", name: "Viewer", description: "Read-only access to dashboards, sessions, and basic reporting", permissions: (["overview.view", "sessions.view", "prompts.view", "traces.view"]), isSystem: true, memberCount: 5, createdAt: d(180) },
    { externalId: "role-006", name: "Compliance Auditor", description: "Restricted access for external or internal auditors to compliance data and audit trails", permissions: (["audit.view", "audit.export", "compliance.view", "integrity.verify"]), isSystem: false, memberCount: 2, createdAt: d(60) },
    { externalId: "role-007", name: "Incident Responder", description: "Elevated access during incidents including escalation handling, session override, and emergency policy bypass", permissions: (["sessions.view", "sessions.respond", "escalations.review", "escalations.override", "prompts.respond", "traces.view", "policies.view"]), isSystem: false, memberCount: 4, createdAt: d(90) },
    { externalId: "role-008", name: "API Consumer", description: "Programmatic access only via API keys with scoped permissions for integration purposes", permissions: (["api.read", "sessions.view", "overview.view"]), isSystem: false, memberCount: 3, createdAt: d(45) },
  ]);

  await db.insert(groups).values([
    { externalId: "grp-001", name: "Platform Engineering", description: "Core platform team responsible for infrastructure and tooling", memberCount: 6, roles: (["Operator", "Viewer"]), permissionLevel: "read-write", createdAt: d(150), syncSource: "LDAP", lastSynced: m(30) },
    { externalId: "grp-002", name: "Security Team", description: "Information security and compliance team", memberCount: 4, roles: (["Security Officer", "Compliance Auditor"]), permissionLevel: "admin", createdAt: d(150), syncSource: "LDAP", lastSynced: m(30) },
    { externalId: "grp-003", name: "SRE / On-Call", description: "Site reliability engineering and incident response team", memberCount: 5, roles: (["Incident Responder", "Operator"]), permissionLevel: "read-write", createdAt: d(120), syncSource: "LDAP", lastSynced: m(30) },
    { externalId: "grp-004", name: "DevOps Leads", description: "Senior engineers with elevated access for cross-team coordination", memberCount: 3, roles: (["Org Admin", "Operator"]), permissionLevel: "admin", createdAt: d(140), syncSource: "Manual", lastSynced: isoNow },
    { externalId: "grp-005", name: "External Auditors", description: "Third-party audit and compliance review team", memberCount: 2, roles: (["Compliance Auditor"]), permissionLevel: "read", createdAt: d(60), syncSource: "Manual", lastSynced: isoNow },
    { externalId: "grp-006", name: "CI/CD Integrations", description: "Service accounts for automated pipeline integrations", memberCount: 3, roles: (["API Consumer"]), permissionLevel: "read", createdAt: d(45), syncSource: "Manual", lastSynced: isoNow },
    { externalId: "grp-007", name: "Executive Stakeholders", description: "Leadership and management with dashboard view access", memberCount: 4, roles: (["Viewer"]), permissionLevel: "read", createdAt: d(100), syncSource: "SAML", lastSynced: h(2) },
  ]);

  await db.insert(users).values([
    { externalId: "usr-001", username: "j.martinez", email: "j.martinez@atlasbridge.local", displayName: "Jordan Martinez", role: "Super Admin", status: "active", mfaStatus: "enforced", lastActive: m(5), createdAt: d(180), groups: (["DevOps Leads"]), loginMethod: "SSO + Hardware Key" },
    { externalId: "usr-002", username: "s.nakamura", email: "s.nakamura@atlasbridge.local", displayName: "Suki Nakamura", role: "Super Admin", status: "active", mfaStatus: "enforced", lastActive: m(15), createdAt: d(180), groups: (["Platform Engineering", "DevOps Leads"]), loginMethod: "SSO + Hardware Key" },
    { externalId: "usr-003", username: "a.okonkwo", email: "a.okonkwo@atlasbridge.local", displayName: "Adaeze Okonkwo", role: "Org Admin", status: "active", mfaStatus: "enforced", lastActive: m(45), createdAt: d(160), groups: (["DevOps Leads"]), loginMethod: "SSO + TOTP" },
    { externalId: "usr-004", username: "m.chen", email: "m.chen@atlasbridge.local", displayName: "Michael Chen", role: "Security Officer", status: "active", mfaStatus: "enforced", lastActive: h(1), createdAt: d(150), groups: (["Security Team"]), loginMethod: "SSO + TOTP" },
    { externalId: "usr-005", username: "r.patel", email: "r.patel@atlasbridge.local", displayName: "Riya Patel", role: "Operator", status: "active", mfaStatus: "enabled", lastActive: m(20), createdAt: d(120), groups: (["Platform Engineering", "SRE / On-Call"]), loginMethod: "SSO" },
    { externalId: "usr-006", username: "k.johansson", email: "k.johansson@atlasbridge.local", displayName: "Karl Johansson", role: "Operator", status: "active", mfaStatus: "enabled", lastActive: m(35), createdAt: d(110), groups: (["SRE / On-Call"]), loginMethod: "SSO" },
    { externalId: "usr-007", username: "l.kim", email: "l.kim@atlasbridge.local", displayName: "Lisa Kim", role: "Incident Responder", status: "active", mfaStatus: "enabled", lastActive: h(2), createdAt: d(90), groups: (["SRE / On-Call"]), loginMethod: "SSO + TOTP" },
    { externalId: "usr-008", username: "d.wright", email: "d.wright@atlasbridge.local", displayName: "Daniel Wright", role: "Operator", status: "active", mfaStatus: "enabled", lastActive: h(3), createdAt: d(100), groups: (["Platform Engineering"]), loginMethod: "SSO" },
    { externalId: "usr-009", username: "e.garcia", email: "e.garcia@atlasbridge.local", displayName: "Elena Garcia", role: "Security Officer", status: "active", mfaStatus: "enforced", lastActive: h(4), createdAt: d(80), groups: (["Security Team"]), loginMethod: "SSO + Hardware Key" },
    { externalId: "usr-010", username: "t.williams", email: "t.williams@atlasbridge.local", displayName: "Tyrone Williams", role: "Org Admin", status: "active", mfaStatus: "enforced", lastActive: h(1), createdAt: d(140), groups: (["Platform Engineering", "DevOps Leads"]), loginMethod: "SSO + TOTP" },
    { externalId: "usr-011", username: "n.petrov", email: "n.petrov@atlasbridge.local", displayName: "Nikolai Petrov", role: "Compliance Auditor", status: "active", mfaStatus: "enabled", lastActive: d(2), createdAt: d(55), groups: (["External Auditors"]), loginMethod: "SSO" },
    { externalId: "usr-012", username: "c.dubois", email: "c.dubois@atlasbridge.local", displayName: "Claire Dubois", role: "Compliance Auditor", status: "active", mfaStatus: "enabled", lastActive: d(3), createdAt: d(50), groups: (["External Auditors"]), loginMethod: "SSO" },
    { externalId: "usr-013", username: "f.ahmed", email: "f.ahmed@atlasbridge.local", displayName: "Fatima Ahmed", role: "Operator", status: "active", mfaStatus: "enabled", lastActive: m(50), createdAt: d(85), groups: (["Platform Engineering"]), loginMethod: "SSO" },
    { externalId: "usr-014", username: "b.silva", email: "b.silva@atlasbridge.local", displayName: "Bruno Silva", role: "Viewer", status: "active", mfaStatus: "disabled", lastActive: d(1), createdAt: d(70), groups: (["Executive Stakeholders"]), loginMethod: "SSO" },
    { externalId: "usr-015", username: "w.zhao", email: "w.zhao@atlasbridge.local", displayName: "Wei Zhao", role: "Operator", status: "inactive", mfaStatus: "disabled", lastActive: d(30), createdAt: d(100), groups: (["Platform Engineering"]), loginMethod: "SSO" },
    { externalId: "usr-016", username: "svc-cicd-main", email: "svc@atlasbridge.local", displayName: "CI/CD Pipeline (Main)", role: "API Consumer", status: "active", mfaStatus: "disabled", lastActive: m(10), createdAt: d(45), groups: (["CI/CD Integrations"]), loginMethod: "API Key" },
    { externalId: "usr-017", username: "svc-cicd-staging", email: "svc-stg@atlasbridge.local", displayName: "CI/CD Pipeline (Staging)", role: "API Consumer", status: "active", mfaStatus: "disabled", lastActive: m(25), createdAt: d(40), groups: (["CI/CD Integrations"]), loginMethod: "API Key" },
    { externalId: "usr-018", username: "p.new", email: "p.new@atlasbridge.local", displayName: "Pending User", role: "Viewer", status: "pending", mfaStatus: "disabled", lastActive: isoNow, createdAt: d(1), groups: ([]), loginMethod: "Invite Pending" },
  ]);

  await db.insert(apiKeys).values([
    { externalId: "key-001", name: "Production CI/CD", prefix: "ab_prod_", scopes: (["sessions.view", "overview.view", "api.read"]), status: "active", createdBy: "j.martinez", createdAt: d(45), expiresAt: futureD(90), lastUsed: m(10), rateLimit: 1000 },
    { externalId: "key-002", name: "Staging CI/CD", prefix: "ab_stg_", scopes: (["sessions.view", "overview.view", "api.read"]), status: "active", createdBy: "j.martinez", createdAt: d(40), expiresAt: futureD(85), lastUsed: m(25), rateLimit: 500 },
    { externalId: "key-003", name: "Monitoring Integration", prefix: "ab_mon_", scopes: (["overview.view", "integrity.verify"]), status: "active", createdBy: "a.okonkwo", createdAt: d(30), expiresAt: futureD(60), lastUsed: h(1), rateLimit: 200 },
    { externalId: "key-004", name: "Compliance Export Tool", prefix: "ab_comp_", scopes: (["audit.view", "audit.export", "compliance.view"]), status: "active", createdBy: "m.chen", createdAt: d(20), expiresAt: futureD(50), lastUsed: d(2), rateLimit: 100 },
    { externalId: "key-005", name: "Legacy Terraform Hook", prefix: "ab_tf_", scopes: (["sessions.view"]), status: "revoked", createdBy: "s.nakamura", createdAt: d(120), expiresAt: d(10), lastUsed: d(15), rateLimit: 300 },
    { externalId: "key-006", name: "Dev Testing Key", prefix: "ab_dev_", scopes: (["*"]), status: "expired", createdBy: "r.patel", createdAt: d(90), expiresAt: d(5), lastUsed: d(10), rateLimit: 50 },
  ]);

  await db.insert(securityPolicies).values([
    { externalId: "sp-001", name: "MFA Requirement", category: "Authentication", description: "Multi-factor authentication requirement for all user accounts", enabled: true, value: "Required for Admin roles, recommended for all", severity: "critical" },
    { externalId: "sp-002", name: "Password Complexity", category: "Authentication", description: "Minimum password requirements for local accounts", enabled: true, value: "Min 16 chars, uppercase, lowercase, number, symbol", severity: "critical" },
    { externalId: "sp-003", name: "Session Timeout", category: "Session Management", description: "Maximum idle session duration before automatic logout", enabled: true, value: "30 minutes", severity: "warning" },
    { externalId: "sp-004", name: "Failed Login Lockout", category: "Authentication", description: "Account lockout after consecutive failed login attempts", enabled: true, value: "5 attempts, 15 min lockout", severity: "critical" },
    { externalId: "sp-005", name: "IP Allowlist", category: "Network", description: "Restrict access to configured IP ranges only", enabled: true, value: "4 ranges configured", severity: "critical" },
    { externalId: "sp-006", name: "API Rate Limiting", category: "API Security", description: "Per-key rate limiting for API access", enabled: true, value: "50-1000 req/min per key", severity: "warning" },
    { externalId: "sp-007", name: "Token Auto-Rotation", category: "API Security", description: "Automatic rotation of API tokens at configured intervals", enabled: true, value: "Every 90 days", severity: "warning" },
    { externalId: "sp-008", name: "Audit Log Immutability", category: "Compliance", description: "Prevent modification or deletion of audit log entries", enabled: true, value: "Write-once, append-only", severity: "critical" },
    { externalId: "sp-009", name: "Secret Auto-Redaction", category: "Data Protection", description: "Automatic redaction of secrets and tokens in logs and UI", enabled: true, value: "Pattern-based + ML-assisted", severity: "critical" },
    { externalId: "sp-010", name: "Cross-Origin Restrictions", category: "Network", description: "CORS policy for API endpoints", enabled: true, value: "Same-origin only", severity: "warning" },
    { externalId: "sp-011", name: "TLS Minimum Version", category: "Network", description: "Minimum TLS version for all connections", enabled: true, value: "TLS 1.3", severity: "critical" },
    { externalId: "sp-012", name: "Privilege Escalation Alert", category: "Access Control", description: "Alert on any role or permission changes to admin-level accounts", enabled: true, value: "Immediate alert to Security Team", severity: "critical" },
    { externalId: "sp-013", name: "Inactive Account Cleanup", category: "Account Lifecycle", description: "Auto-deactivate accounts after prolonged inactivity", enabled: true, value: "90 days", severity: "info" },
    { externalId: "sp-014", name: "Concurrent Session Limit", category: "Session Management", description: "Maximum number of concurrent active sessions per user", enabled: true, value: "3 sessions", severity: "warning" },
    { externalId: "sp-015", name: "Data Export Approval", category: "Data Protection", description: "Require approval for bulk data exports from audit and compliance", enabled: false, value: "Disabled", severity: "info" },
  ]);

  await db.insert(notifications).values([
    { externalId: "notif-001", channel: "slack", name: "Ops Alerts Channel", enabled: true, destination: "#atlasbridge-ops-alerts", events: (["escalation.created", "session.critical", "integrity.warning"]), minSeverity: "high", lastDelivered: m(5) },
    { externalId: "notif-002", channel: "slack", name: "Security Channel", enabled: true, destination: "#security-incidents", events: (["escalation.critical", "integrity.failed", "policy.violation"]), minSeverity: "critical", lastDelivered: h(1) },
    { externalId: "notif-003", channel: "email", name: "Admin Digest", enabled: true, destination: "admin-team@atlasbridge.local", events: (["daily.summary", "user.created", "role.changed"]), minSeverity: "info", lastDelivered: h(6) },
    { externalId: "notif-004", channel: "pagerduty", name: "On-Call Escalation", enabled: true, destination: "service-key: [REDACTED]", events: (["escalation.critical", "session.unresponsive"]), minSeverity: "critical", lastDelivered: d(3) },
    { externalId: "notif-005", channel: "webhook", name: "SIEM Integration", enabled: true, destination: "https://siem.atlasbridge.local/api/ingest", events: (["*"]), minSeverity: "low", lastDelivered: m(1) },
    { externalId: "notif-006", channel: "email", name: "Compliance Reports", enabled: true, destination: "compliance@atlasbridge.local", events: (["compliance.report", "audit.export"]), minSeverity: "info", lastDelivered: d(7) },
    { externalId: "notif-007", channel: "opsgenie", name: "Critical Alert Routing", enabled: false, destination: "team-key: [REDACTED]", events: (["escalation.critical"]), minSeverity: "critical", lastDelivered: d(30) },
  ]);

  await db.insert(ipAllowlist).values([
    { externalId: "ip-001", cidr: "10.0.0.0/8", label: "Internal Network", addedBy: "j.martinez", addedAt: d(180), lastHit: m(1) },
    { externalId: "ip-002", cidr: "172.16.0.0/12", label: "VPN Range", addedBy: "j.martinez", addedAt: d(180), lastHit: m(3) },
    { externalId: "ip-003", cidr: "192.168.1.0/24", label: "Office WiFi", addedBy: "a.okonkwo", addedAt: d(90), lastHit: h(1) },
    { externalId: "ip-004", cidr: "127.0.0.1/32", label: "Localhost", addedBy: "system", addedAt: d(180), lastHit: isoNow },
  ]);

  console.log("Database seeded successfully");
}
