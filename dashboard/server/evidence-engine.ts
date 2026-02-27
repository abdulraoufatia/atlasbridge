import { createHash } from "crypto";
import { repo } from "./atlasbridge-repo";

const SECRET_PATTERNS = [
  /sk[-_][a-zA-Z0-9]{20,}/g,
  /Bearer\s+[a-zA-Z0-9._\-]+/g,
  /ghp_[a-zA-Z0-9]{36}/g,
  /glpat-[a-zA-Z0-9\-_]{20,}/g,
  /xoxb-[a-zA-Z0-9\-]+/g,
  /-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(RSA\s+)?PRIVATE\s+KEY-----/g,
  /[a-zA-Z0-9+/]{40,}={0,2}/g,
  /api[_-]?key[=:\s]+["']?[a-zA-Z0-9]{16,}["']?/gi,
  /password[=:\s]+["']?[^\s"']+["']?/gi,
  /secret[=:\s]+["']?[a-zA-Z0-9]{16,}["']?/gi,
  /token[=:\s]+["']?[a-zA-Z0-9._\-]{20,}["']?/gi,
];

export function redactSecrets(input: string): string {
  let result = input;
  for (const pattern of SECRET_PATTERNS) {
    result = result.replace(pattern, "[REDACTED]");
  }
  return result;
}

function sha256(data: string): string {
  return createHash("sha256").update(data).digest("hex");
}

export interface EvidenceDecision {
  id: string;
  timestamp: string;
  sessionId: string;
  type: string;
  decision: string;
  confidence: number;
  actionTaken: string;
  content: string;
}

export interface EvidenceEscalation {
  id: string;
  timestamp: string;
  sessionId: string;
  riskLevel: string;
  message: string;
  actionTaken: string;
}

export interface IntegrityReport {
  overallStatus: string;
  lastVerifiedAt: string;
  components: {
    component: string;
    status: string;
    hash: string;
    lastChecked: string;
    details: string;
  }[];
  hashChainValid: boolean;
  totalTraceEntries: number;
  traceHashSummary: string;
}

export interface EvidenceBundle {
  generatedAt: string;
  sessionId?: string;
  decisions: EvidenceDecision[];
  escalations: EvidenceEscalation[];
  integrityReport: IntegrityReport;
  replayReferences: { sessionId: string; traceCount: number; tool: string; status: string }[];
  policySnapshot: { name: string; hash: string }[];
  governanceScore: GovernanceScore;
}

export interface GovernanceScore {
  overall: number;
  autonomousRate: number;
  escalationRate: number;
  blockedHighRisk: number;
  policyCoverage: number;
  sessionCount: number;
  decisionCount: number;
  computedAt: string;
}

export function computeGovernanceScore(sessionFilter?: string): GovernanceScore {
  const allPrompts = repo.listPrompts();
  const allTraces = repo.listTraces();
  const allSessions = repo.listSessions();

  const relevantPrompts = sessionFilter
    ? allPrompts.filter(p => p.sessionId === sessionFilter)
    : allPrompts;
  const relevantTraces = sessionFilter
    ? allTraces.filter(t => t.sessionId === sessionFilter)
    : allTraces;
  const relevantSessions = sessionFilter
    ? allSessions.filter(s => s.id === sessionFilter)
    : allSessions;

  const totalDecisions = relevantPrompts.length;
  const autoDecisions = relevantPrompts.filter(p => p.decision === "auto").length;
  const escalatedDecisions = relevantPrompts.filter(p => p.decision === "escalated").length;
  const blockedTraces = relevantTraces.filter(t => t.action === "blocked" || t.action === "escalated" || t.action === "require_human").length;
  const matchedTraces = relevantTraces.filter(t => t.ruleMatched !== "default").length;

  const autonomousRate = totalDecisions > 0 ? Math.round((autoDecisions / totalDecisions) * 1000) / 10 : 0;
  const escalationRate = totalDecisions > 0 ? Math.round((escalatedDecisions / totalDecisions) * 1000) / 10 : 0;
  const policyCoverage = relevantTraces.length > 0 ? Math.round((matchedTraces / relevantTraces.length) * 1000) / 10 : 0;

  const overall = Math.round(
    (autonomousRate * 0.3 + (100 - escalationRate) * 0.25 + policyCoverage * 0.25 + Math.min(blockedTraces * 5, 100) * 0.2) * 10
  ) / 10;

  return {
    overall: Math.min(overall, 100),
    autonomousRate,
    escalationRate,
    blockedHighRisk: blockedTraces,
    policyCoverage,
    sessionCount: relevantSessions.length,
    decisionCount: totalDecisions,
    computedAt: new Date().toISOString(),
  };
}

export function generateEvidenceJSON(sessionId?: string): EvidenceBundle {
  const allPrompts = repo.listPrompts();
  const allAudit = repo.listAuditEvents();
  const allSessions = repo.listSessions();
  const allTraces = repo.listTraces();
  const integrityData = repo.getIntegrity();

  const relevantPrompts = sessionId
    ? allPrompts.filter(p => p.sessionId === sessionId)
    : allPrompts;
  const relevantAudit = sessionId
    ? allAudit.filter(a => a.sessionId === sessionId)
    : allAudit;

  const decisions: EvidenceDecision[] = relevantPrompts.map(p => ({
    id: p.id,
    timestamp: p.timestamp,
    sessionId: p.sessionId,
    type: p.type,
    decision: p.decision,
    confidence: p.confidence,
    actionTaken: p.actionTaken,
    content: redactSecrets(p.content),
  }));

  const escalations: EvidenceEscalation[] = relevantAudit
    .filter(a => a.actionTaken === "escalated" || a.actionTaken === "denied" || a.actionTaken === "prompt_escalated")
    .map(a => ({
      id: a.id,
      timestamp: a.timestamp,
      sessionId: a.sessionId,
      riskLevel: a.riskLevel,
      message: redactSecrets(a.message),
      actionTaken: a.actionTaken,
    }));

  const traceHashes = allTraces.map(t => t.hash).join(",");

  const integrityReport: IntegrityReport = {
    overallStatus: integrityData.overallStatus,
    lastVerifiedAt: integrityData.lastVerifiedAt,
    components: integrityData.results.map(r => ({
      component: r.component,
      status: r.status,
      hash: r.hash,
      lastChecked: r.lastChecked,
      details: r.details,
    })),
    hashChainValid: integrityData.overallStatus === "Verified",
    totalTraceEntries: allTraces.length,
    traceHashSummary: sha256(traceHashes),
  };

  const replayReferences = allSessions.map(s => ({
    sessionId: s.id,
    traceCount: allTraces.filter(t => t.sessionId === s.id).length,
    tool: s.tool,
    status: s.status,
  }));

  // Collect unique rule IDs from traces for policy snapshot
  const ruleIds = Array.from(new Set(allTraces.map(t => t.ruleMatched).filter(r => r && r !== "default")));
  const policySnapshot = ruleIds.length > 0
    ? ruleIds.map(name => ({ name, hash: sha256(name + ":v1.1.0") }))
    : [{ name: "default", hash: sha256("default:v1.1.0") }];

  return {
    generatedAt: new Date().toISOString(),
    sessionId,
    decisions,
    escalations,
    integrityReport,
    replayReferences,
    policySnapshot,
    governanceScore: computeGovernanceScore(sessionId),
  };
}

export function generateEvidenceCSV(sessionId?: string): string {
  const bundle = generateEvidenceJSON(sessionId);

  const lines: string[] = [];
  lines.push("type,id,timestamp,sessionId,decision,confidence,riskLevel,actionTaken,content");

  for (const d of bundle.decisions) {
    lines.push([
      "decision",
      d.id,
      d.timestamp,
      d.sessionId,
      d.decision,
      String(d.confidence),
      "",
      d.actionTaken,
      `"${d.content.replace(/"/g, '""')}"`,
    ].join(","));
  }

  for (const e of bundle.escalations) {
    lines.push([
      "escalation",
      e.id,
      e.timestamp,
      e.sessionId,
      "",
      "",
      e.riskLevel,
      e.actionTaken,
      `"${e.message.replace(/"/g, '""')}"`,
    ].join(","));
  }

  return lines.join("\n");
}

export interface EvidenceManifest {
  version: string;
  generatedAt: string;
  sessionId?: string;
  files: { filename: string; sha256: string; sizeBytes: number }[];
  disclaimer: string;
}

export function generateEvidenceManifest(bundle: EvidenceBundle, csv: string): EvidenceManifest {
  const evidenceJson = JSON.stringify(bundle, null, 2);
  const integrityJson = JSON.stringify(bundle.integrityReport, null, 2);
  const readmeText = generateReadmeText();

  return {
    version: "1.0.0",
    generatedAt: bundle.generatedAt,
    sessionId: bundle.sessionId,
    files: [
      { filename: "evidence.json", sha256: sha256(evidenceJson), sizeBytes: Buffer.byteLength(evidenceJson) },
      { filename: "decisions.csv", sha256: sha256(csv), sizeBytes: Buffer.byteLength(csv) },
      { filename: "integrity_report.json", sha256: sha256(integrityJson), sizeBytes: Buffer.byteLength(integrityJson) },
      { filename: "README.txt", sha256: sha256(readmeText), sizeBytes: Buffer.byteLength(readmeText) },
    ],
    disclaimer: "AtlasBridge produces verifiable decision evidence; it does not certify compliance with any external framework.",
  };
}

function generateReadmeText(): string {
  return `AtlasBridge Governance Evidence Bundle
======================================

This bundle contains verifiable governance evidence generated by AtlasBridge,
a deterministic governance runtime for AI execution.

Contents:
- evidence.json       Complete evidence export (decisions, escalations, integrity, replay refs)
- decisions.csv       Tabular export of decisions and escalations
- integrity_report.json  Hash-chain integrity verification summary
- manifest.json       File manifest with SHA-256 hashes for verification

Verification:
To verify the integrity of this bundle, compute SHA-256 hashes for each file
and compare them against the hashes listed in manifest.json.

IMPORTANT DISCLAIMER:
AtlasBridge produces verifiable decision evidence; it does not certify compliance
with any external framework. This evidence may support audit narratives, but it
does not constitute certification or attestation. Users are responsible for their
own programmes.

All secrets and sensitive tokens have been redacted from this export.
`;
}

export function generateFullBundle(sessionId?: string): {
  evidence: EvidenceBundle;
  csv: string;
  integrityReport: IntegrityReport;
  manifest: EvidenceManifest;
  readme: string;
} {
  const evidence = generateEvidenceJSON(sessionId);
  const csv = generateEvidenceCSV(sessionId);
  const manifest = generateEvidenceManifest(evidence, csv);
  return {
    evidence,
    csv,
    integrityReport: evidence.integrityReport,
    manifest,
    readme: generateReadmeText(),
  };
}

export interface PolicyPack {
  id: string;
  name: string;
  category: string;
  description: string;
  disclaimer: string;
  policies: { name: string; action: string; description: string }[];
}

export const policyPacks: PolicyPack[] = [
  {
    id: "high-assurance-mode",
    name: "High-Assurance Mode",
    category: "Assurance",
    disclaimer: "This policy pack enforces strict governance behaviours. It does not certify compliance with any external framework.",
    description: "Require human approval for high-risk operations, strict session recording, and comprehensive audit logging.",
    policies: [
      { name: "require_human_high_risk", action: "require_human", description: "Require human approval for all high-risk and critical operations" },
      { name: "session_recording", action: "enforce", description: "Record all agent sessions for audit trail" },
      { name: "audit_retention_730d", action: "enforce", description: "Retain audit logs for minimum 730 days" },
      { name: "access_review_quarterly", action: "advisory", description: "Advisory: schedule quarterly access reviews" },
      { name: "change_management_logging", action: "enforce", description: "Log all configuration and policy changes" },
    ],
  },
  {
    id: "strict-access-control",
    name: "Strict Access Control",
    category: "Access",
    disclaimer: "This policy pack enforces strict access controls and integrity verification. It does not certify compliance with any external framework.",
    description: "Strict access controls, risk-based escalation, and integrity verification for security-sensitive environments.",
    policies: [
      { name: "risk_based_escalation", action: "require_human", description: "Escalate decisions above medium risk threshold" },
      { name: "integrity_verification", action: "enforce", description: "Run integrity checks on all components hourly" },
      { name: "secret_redaction", action: "enforce", description: "Auto-redact secrets in all logs and exports" },
      { name: "encryption_at_rest", action: "enforce", description: "Enforce encryption for all stored data" },
      { name: "incident_response_logging", action: "enforce", description: "Log all security-relevant events with full context" },
      { name: "access_control_strict", action: "enforce", description: "Apply principle of least privilege to all agent operations" },
    ],
  },
  {
    id: "data-protection-mode",
    name: "Data Protection Mode",
    category: "Data",
    disclaimer: "This policy pack provides data protection governance behaviours. It does not certify compliance with any external framework.",
    description: "Strict data handling, enhanced redaction, and minimum necessary access for sensitive data environments.",
    policies: [
      { name: "sensitive_data_redaction", action: "enforce", description: "Enhanced redaction rules for sensitive data patterns" },
      { name: "minimum_necessary_access", action: "require_human", description: "Require human approval for broad data access operations" },
      { name: "audit_trail_complete", action: "enforce", description: "Complete audit trail for all data access and modifications" },
      { name: "session_timeout_strict", action: "enforce", description: "Strict 15-minute inactivity timeout" },
      { name: "data_encryption_transit", action: "enforce", description: "Enforce encryption in transit for all communications" },
    ],
  },
  {
    id: "minimal-logging-mode",
    name: "Minimal Logging Mode",
    category: "Retention",
    disclaimer: "This policy pack restricts logging to the minimum necessary for governance. It does not certify compliance with any external framework.",
    description: "Restrict logging and data handling to the minimum necessary: redact PII, limit retention, and enforce data minimisation principles.",
    policies: [
      { name: "pii_redaction", action: "enforce", description: "Redact personally identifiable information from all logs" },
      { name: "data_minimization", action: "enforce", description: "Log only minimum necessary data for governance purposes" },
      { name: "retention_limit_365d", action: "enforce", description: "Limit data retention to 365 days maximum" },
      { name: "consent_logging", action: "advisory", description: "Advisory: log consent basis for data processing" },
      { name: "right_to_erasure_support", action: "advisory", description: "Advisory: support data deletion requests in agent logs" },
    ],
  },
];

export interface EvidenceBundleListItem {
  id: string;
  generatedAt: string;
  sessionId?: string;
  format: "json" | "csv" | "bundle";
  decisionCount: number;
  escalationCount: number;
  integrityStatus: string;
  governanceScore: number;
  manifestHash?: string;
}

let generatedBundles: EvidenceBundleListItem[] = [];

export function listGeneratedBundles(): EvidenceBundleListItem[] {
  return generatedBundles;
}

export function addGeneratedBundle(item: Omit<EvidenceBundleListItem, "id">): EvidenceBundleListItem {
  const entry: EvidenceBundleListItem = {
    ...item,
    id: `evb-${Date.now()}`,
  };
  generatedBundles = [entry, ...generatedBundles];
  return entry;
}
