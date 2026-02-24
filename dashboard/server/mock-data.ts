import type {
  OverviewData, Session, SessionDetail, PromptEntry,
  TraceEntry, IntegrityData, AuditEntry, SettingsData,
  ActivityEvent, RuleTriggered, RbacPermission, OrgProfile,
  SsoConfig, ComplianceConfig, SessionPolicyConfig
} from "@shared/schema";

const now = new Date();
const h = (hoursAgo: number) => new Date(now.getTime() - hoursAgo * 3600000).toISOString();
const m = (minsAgo: number) => new Date(now.getTime() - minsAgo * 60000).toISOString();

export const sessions: Session[] = [
  { id: "sess-a1b2c3d4", tool: "GitHub Actions", startTime: h(6), lastActivity: m(3), status: "running", riskLevel: "low", escalationsCount: 0, ciSnapshot: "pass" },
  { id: "sess-e5f6g7h8", tool: "Terraform", startTime: h(4), lastActivity: m(12), status: "running", riskLevel: "medium", escalationsCount: 1, ciSnapshot: "pass" },
  { id: "sess-i9j0k1l2", tool: "Docker Compose", startTime: h(8), lastActivity: m(45), status: "running", riskLevel: "low", escalationsCount: 0, ciSnapshot: "pass" },
  { id: "sess-m3n4o5p6", tool: "kubectl", startTime: h(2), lastActivity: m(5), status: "running", riskLevel: "high", escalationsCount: 3, ciSnapshot: "fail" },
  { id: "sess-q7r8s9t0", tool: "AWS CLI", startTime: h(12), lastActivity: h(1), status: "stopped", riskLevel: "critical", escalationsCount: 5, ciSnapshot: "fail" },
  { id: "sess-u1v2w3x4", tool: "Ansible", startTime: h(3), lastActivity: m(20), status: "running", riskLevel: "low", escalationsCount: 0, ciSnapshot: "pass" },
  { id: "sess-y5z6a7b8", tool: "Helm", startTime: h(5), lastActivity: m(55), status: "stopped", riskLevel: "medium", escalationsCount: 2, ciSnapshot: "unknown" },
  { id: "sess-c9d0e1f2", tool: "Pulumi", startTime: h(1), lastActivity: m(8), status: "running", riskLevel: "low", escalationsCount: 0, ciSnapshot: "pass" },
];

export const prompts: PromptEntry[] = [
  { id: "pmt-001", type: "yes_no", confidence: 0.95, decision: "auto", actionTaken: "approved", timestamp: m(3), sessionId: "sess-a1b2c3d4", content: "Deploy latest build to staging?" },
  { id: "pmt-002", type: "confirm_enter", confidence: 0.72, decision: "human", actionTaken: "confirmed", timestamp: m(8), sessionId: "sess-e5f6g7h8", content: "Apply Terraform plan with 3 resource changes?" },
  { id: "pmt-003", type: "numbered_choice", confidence: 0.88, decision: "auto", actionTaken: "selected_option_2", timestamp: m(12), sessionId: "sess-i9j0k1l2", content: "Select container restart policy" },
  { id: "pmt-004", type: "yes_no", confidence: 0.31, decision: "escalated", actionTaken: "escalated_to_ops", timestamp: m(5), sessionId: "sess-m3n4o5p6", content: "Scale deployment to 12 replicas in production?" },
  { id: "pmt-005", type: "free_text", confidence: 0.65, decision: "human", actionTaken: "input_provided", timestamp: m(15), sessionId: "sess-q7r8s9t0", content: "Specify IAM role ARN for cross-account access" },
  { id: "pmt-006", type: "yes_no", confidence: 0.99, decision: "auto", actionTaken: "approved", timestamp: m(20), sessionId: "sess-u1v2w3x4", content: "Run Ansible playbook on dev inventory?" },
  { id: "pmt-007", type: "confirm_enter", confidence: 0.45, decision: "escalated", actionTaken: "escalated_to_security", timestamp: m(22), sessionId: "sess-q7r8s9t0", content: "Delete S3 bucket with versioning enabled?" },
  { id: "pmt-008", type: "multi_select", confidence: 0.82, decision: "auto", actionTaken: "selected_items", timestamp: m(30), sessionId: "sess-y5z6a7b8", content: "Select Helm values to override" },
  { id: "pmt-009", type: "yes_no", confidence: 0.91, decision: "auto", actionTaken: "approved", timestamp: m(35), sessionId: "sess-c9d0e1f2", content: "Create new Pulumi stack for dev environment?" },
  { id: "pmt-010", type: "numbered_choice", confidence: 0.28, decision: "escalated", actionTaken: "escalated_to_lead", timestamp: m(40), sessionId: "sess-m3n4o5p6", content: "Choose rollback strategy for failed deployment" },
  { id: "pmt-011", type: "yes_no", confidence: 0.87, decision: "auto", actionTaken: "approved", timestamp: m(50), sessionId: "sess-a1b2c3d4", content: "Merge PR #247 into main?" },
  { id: "pmt-012", type: "confirm_enter", confidence: 0.76, decision: "human", actionTaken: "confirmed", timestamp: m(55), sessionId: "sess-e5f6g7h8", content: "Destroy and recreate RDS instance?" },
  { id: "pmt-013", type: "free_text", confidence: 0.58, decision: "human", actionTaken: "input_provided", timestamp: h(1.1), sessionId: "sess-i9j0k1l2", content: "Enter Docker image tag for rollback" },
  { id: "pmt-014", type: "yes_no", confidence: 0.93, decision: "auto", actionTaken: "approved", timestamp: h(1.5), sessionId: "sess-u1v2w3x4", content: "Apply security patches to all hosts?" },
  { id: "pmt-015", type: "multi_select", confidence: 0.41, decision: "escalated", actionTaken: "escalated_to_ops", timestamp: h(2), sessionId: "sess-q7r8s9t0", content: "Select EC2 instances for termination" },
];

export const traces: TraceEntry[] = Array.from({ length: 40 }, (_, i) => {
  const riskLevels: Array<"low" | "medium" | "high" | "critical"> = ["low", "low", "low", "medium", "medium", "high", "critical"];
  const rules = [
    "policy.cost_threshold", "policy.blast_radius", "policy.prod_access",
    "policy.data_retention", "policy.secret_exposure", "policy.resource_limit",
    "policy.network_egress", "policy.iam_escalation", "policy.compliance_check",
    "policy.drift_detection"
  ];
  const actions = [
    "allowed", "allowed", "allowed", "flagged", "flagged",
    "blocked", "escalated", "logged", "deferred", "allowed"
  ];
  const sessionIds = sessions.map(s => s.id);
  return {
    id: `trace-${String(i + 1).padStart(3, "0")}`,
    hash: `sha256:${Array.from({ length: 12 }, () => Math.random().toString(16).slice(2, 4)).join("")}`,
    stepIndex: i + 1,
    riskLevel: riskLevels[i % riskLevels.length],
    ruleMatched: rules[i % rules.length],
    action: actions[i % actions.length],
    timestamp: m(i * 4 + 1),
    sessionId: sessionIds[i % sessionIds.length],
  };
});

const recentActivity: ActivityEvent[] = [
  { id: "evt-001", timestamp: m(3), type: "session.heartbeat", message: "GitHub Actions session heartbeat received", riskLevel: "low", sessionId: "sess-a1b2c3d4" },
  { id: "evt-002", timestamp: m(5), type: "prompt.escalated", message: "Kubernetes scale operation escalated to ops team", riskLevel: "high", sessionId: "sess-m3n4o5p6" },
  { id: "evt-003", timestamp: m(8), type: "prompt.resolved", message: "Terraform plan confirmed by human operator", riskLevel: "medium", sessionId: "sess-e5f6g7h8" },
  { id: "evt-004", timestamp: m(12), type: "policy.triggered", message: "Cost threshold policy triggered for AWS resource", riskLevel: "medium" },
  { id: "evt-005", timestamp: m(15), type: "session.stopped", message: "AWS CLI session stopped after critical escalation", riskLevel: "critical", sessionId: "sess-q7r8s9t0" },
  { id: "evt-006", timestamp: m(20), type: "prompt.auto", message: "Ansible playbook auto-approved for dev environment", riskLevel: "low", sessionId: "sess-u1v2w3x4" },
  { id: "evt-007", timestamp: m(22), type: "integrity.check", message: "Integrity verification completed successfully", riskLevel: "low" },
  { id: "evt-008", timestamp: m(30), type: "prompt.resolved", message: "Helm values override selected automatically", riskLevel: "low", sessionId: "sess-y5z6a7b8" },
  { id: "evt-009", timestamp: m(35), type: "session.started", message: "Pulumi session initialized for dev stack", riskLevel: "low", sessionId: "sess-c9d0e1f2" },
  { id: "evt-010", timestamp: m(40), type: "prompt.escalated", message: "Rollback strategy decision escalated to lead", riskLevel: "high", sessionId: "sess-m3n4o5p6" },
  { id: "evt-011", timestamp: m(45), type: "policy.triggered", message: "Blast radius policy triggered for Terraform destroy", riskLevel: "high" },
  { id: "evt-012", timestamp: m(50), type: "prompt.auto", message: "PR merge auto-approved with passing CI checks", riskLevel: "low", sessionId: "sess-a1b2c3d4" },
  { id: "evt-013", timestamp: m(55), type: "session.heartbeat", message: "Helm session heartbeat timeout detected", riskLevel: "medium", sessionId: "sess-y5z6a7b8" },
  { id: "evt-014", timestamp: h(1), type: "prompt.escalated", message: "S3 bucket deletion escalated to security team", riskLevel: "critical", sessionId: "sess-q7r8s9t0" },
  { id: "evt-015", timestamp: h(1.1), type: "integrity.warning", message: "Hash chain drift detected in trace log", riskLevel: "medium" },
  { id: "evt-016", timestamp: h(1.5), type: "prompt.auto", message: "Security patches auto-approved for all hosts", riskLevel: "low", sessionId: "sess-u1v2w3x4" },
  { id: "evt-017", timestamp: h(2), type: "policy.triggered", message: "IAM escalation policy triggered for EC2 termination", riskLevel: "critical", sessionId: "sess-q7r8s9t0" },
  { id: "evt-018", timestamp: h(2.5), type: "session.started", message: "Kubernetes session initialized with elevated risk", riskLevel: "high", sessionId: "sess-m3n4o5p6" },
  { id: "evt-019", timestamp: h(3), type: "prompt.resolved", message: "Docker image rollback tag provided by operator", riskLevel: "low", sessionId: "sess-i9j0k1l2" },
  { id: "evt-020", timestamp: h(4), type: "session.started", message: "Terraform session initialized for infrastructure update", riskLevel: "medium", sessionId: "sess-e5f6g7h8" },
];

const topRulesTriggered: RuleTriggered[] = [
  { ruleId: "rule-001", ruleName: "Cost Threshold Exceeded", count: 12, lastTriggered: m(12) },
  { ruleId: "rule-002", ruleName: "Blast Radius Check", count: 8, lastTriggered: m(45) },
  { ruleId: "rule-003", ruleName: "Production Access Guard", count: 6, lastTriggered: m(5) },
  { ruleId: "rule-004", ruleName: "IAM Escalation Detection", count: 5, lastTriggered: h(2) },
  { ruleId: "rule-005", ruleName: "Secret Exposure Prevention", count: 3, lastTriggered: h(4) },
];

export const overview: OverviewData = {
  activeSessions: sessions.filter(s => s.status === "running").length,
  lastEventTimestamp: m(3),
  escalationRate: 26.7,
  autonomyMode: "Assist",
  highRiskEvents: 7,
  integrityStatus: "Verified",
  recentActivity,
  topRulesTriggered,
  riskBreakdown: { low: 18, medium: 9, high: 5, critical: 3 },
  aiSafety: {
    modelTrustScore: 94.2,
    hallucinationRate: 1.8,
    promptInjectionBlocked: 23,
    biasDetections: 4,
    safetyOverrides: 7,
    avgConfidence: 0.87,
    humanOverrideRate: 14.3,
    trend: "improving",
  },
  compliance: {
    overallScore: 91,
    frameworkScores: [
      { framework: "SOC2", score: 94, maxScore: 100 },
      { framework: "ISO27001", score: 89, maxScore: 100 },
      { framework: "GDPR", score: 92, maxScore: 100 },
    ],
    openFindings: 6,
    resolvedLast30d: 14,
    nextAuditDays: 42,
    policyAdherence: 97.3,
  },
  operational: {
    avgResponseTime: 142,
    uptime: 99.97,
    errorRate: 0.12,
    throughput: 1247,
    p95Latency: 340,
    activeIntegrations: 8,
  },
  insights: [
    { id: "ins-001", category: "safety", type: "positive", title: "AI Trust Score Trending Up", description: "Model trust score has improved 3.2% over the past 7 days, now at 94.2%. Confidence thresholds are well-calibrated.", impact: "medium", actionable: false },
    { id: "ins-002", category: "risk", type: "warning", title: "Escalation Spike Detected", description: "Escalation rate increased to 26.7% in the last 24h, above the 20% threshold. Consider reviewing kubectl and AWS CLI session policies.", impact: "high", actionable: true },
    { id: "ins-003", category: "compliance", type: "recommendation", title: "ISO 27001 Gap in Access Reviews", description: "Quarterly access review is overdue by 8 days. Complete the review to maintain ISO 27001 certification readiness.", impact: "high", actionable: true },
    { id: "ins-004", category: "safety", type: "recommendation", title: "Reduce Human Override Rate", description: "Human override rate at 14.3% suggests some automation thresholds could be adjusted. Analyze overrides on low-risk decisions to optimize.", impact: "medium", actionable: true },
    { id: "ins-005", category: "operations", type: "positive", title: "Uptime Exceeds SLA", description: "System uptime at 99.97% exceeds the 99.9% SLA target. Infrastructure reliability is strong.", impact: "low", actionable: false },
    { id: "ins-006", category: "compliance", type: "warning", title: "6 Open Compliance Findings", description: "There are 6 unresolved compliance findings. Prioritize the 2 critical findings related to data encryption at rest.", impact: "high", actionable: true },
  ],
};

export const integrity: IntegrityData = {
  overallStatus: "Verified",
  lastVerifiedAt: m(22),
  results: [
    { component: "Policy Engine", status: "Verified", hash: "sha256:4a8f1c2e9b3d7f0a", lastChecked: m(22), details: "All policy rules intact and hash-verified" },
    { component: "Decision Trace Store", status: "Verified", hash: "sha256:7e2b5d1f8c4a9e3b", lastChecked: m(22), details: "Hash chain continuous, no gaps detected" },
    { component: "Session Manager", status: "Verified", hash: "sha256:1d9c3e7a5b2f8d4c", lastChecked: m(22), details: "Session state consistent across all adapters" },
    { component: "Audit Logger", status: "Verified", hash: "sha256:6f4a8e2c1b5d9a7e", lastChecked: m(22), details: "All audit entries hash-verified and sequential" },
    { component: "Prompt Resolver", status: "Warning", hash: "sha256:3b7d1f5c9a2e4b8d", lastChecked: m(22), details: "Minor configuration drift detected in escalation thresholds" },
    { component: "Adapter Registry", status: "Verified", hash: "sha256:8c2a6e4b1d5f9c3a", lastChecked: m(22), details: "All registered adapters verified and responsive" },
  ],
};

export const audit: AuditEntry[] = Array.from({ length: 50 }, (_, i) => {
  const riskLevels: Array<"low" | "medium" | "high" | "critical"> = ["low", "low", "medium", "high", "critical"];
  const promptTypes: Array<"yes_no" | "confirm_enter" | "numbered_choice" | "free_text" | "multi_select"> = ["yes_no", "confirm_enter", "numbered_choice", "free_text", "multi_select"];
  const actions = ["approved", "denied", "escalated", "confirmed", "deferred", "auto_approved", "logged"];
  const messages = [
    "Deployment request processed for staging environment",
    "Infrastructure change reviewed and approved by operator",
    "Security policy triggered during resource modification",
    "Escalation routed to on-call team for review",
    "Auto-approval granted based on confidence threshold",
    "Resource deletion request flagged for human review",
    "Configuration drift detected and logged for audit",
    "Access control policy enforced on production resource",
    "Cost threshold exceeded for cloud resource provisioning",
    "Compliance check passed for data retention policy",
  ];
  const sessionIds = sessions.map(s => s.id);
  return {
    id: `audit-${String(i + 1).padStart(3, "0")}`,
    timestamp: m(i * 6 + 1),
    riskLevel: riskLevels[i % riskLevels.length],
    sessionId: sessionIds[i % sessionIds.length],
    promptType: promptTypes[i % promptTypes.length],
    actionTaken: actions[i % actions.length],
    message: messages[i % messages.length],
    hashVerified: i % 7 !== 0,
  };
});

export const settings: SettingsData = {
  configPath: "/etc/atlasbridge/config.yaml",
  dbPath: "/var/lib/atlasbridge/state.db",
  tracePath: "/var/log/atlasbridge/traces/",
  version: "1.4.2-beta",
  environment: "local",
  featureFlags: {
    "auto_escalation": true,
    "hash_chain_verification": true,
    "real_time_streaming": false,
    "multi_adapter_support": true,
    "advanced_analytics": false,
    "policy_hot_reload": true,
    "session_recording": false,
    "compliance_mode": true,
  },
};

const d = (daysAgo: number) => new Date(now.getTime() - daysAgo * 86400000).toISOString();

export const orgSettingsStatic: {
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
    createdAt: d(180),
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
    lastAuditDate: d(45),
    nextAuditDate: d(-45),
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

export function getSessionDetail(id: string): SessionDetail | undefined {
  const session = sessions.find(s => s.id === id);
  if (!session) return undefined;
  const sessionPrompts = prompts.filter(p => p.sessionId === id);
  const sessionTraces = traces.filter(t => t.sessionId === id);
  return {
    ...session,
    metadata: {
      "Adapter": session.tool,
      "PID": String(Math.floor(Math.random() * 50000) + 10000),
      "Working Directory": `/opt/atlasbridge/adapters/${session.tool.toLowerCase().replace(/\s+/g, "-")}`,
      "Config Override": "none",
      "Log Level": "info",
      "Started By": "operator@local",
    },
    prompts: sessionPrompts,
    decisionTrace: sessionTraces,
    explainPanel: session.escalationsCount > 0
      ? `This session triggered ${session.escalationsCount} escalation(s). The primary escalation was triggered by policy rule "policy.prod_access" due to ${session.riskLevel} risk operations detected on the ${session.tool} adapter. Confidence scores below the auto-approval threshold (0.70) required human intervention.`
      : `This session operated within normal parameters. All decisions were auto-approved with confidence scores above the threshold. No escalations were required.`,
    rawView: JSON.stringify({
      session_id: session.id,
      adapter: session.tool,
      status: session.status,
      risk: session.riskLevel,
      escalations: session.escalationsCount,
      token_redacted: "[REDACTED:sk-...]",
      bearer_redacted: "[REDACTED:Bearer ...]",
      trace_count: sessionTraces.length,
      prompt_count: sessionPrompts.length,
    }, null, 2),
  };
}
