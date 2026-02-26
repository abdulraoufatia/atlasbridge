import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the repo module before importing evidence-engine
vi.mock("../atlasbridge-repo", () => ({
  repo: {
    listSessions: vi.fn(),
    listPrompts: vi.fn(),
    listTraces: vi.fn(),
    listAuditEvents: vi.fn(),
    getIntegrity: vi.fn(),
  },
}));

import { repo } from "../atlasbridge-repo";
import {
  redactSecrets,
  computeGovernanceScore,
  generateEvidenceJSON,
  generateEvidenceCSV,
  generateEvidenceManifest,
  generateFullBundle,
  listGeneratedBundles,
  addGeneratedBundle,
  compliancePacks,
} from "../evidence-engine";

const mockSessions = [
  { id: "sess-001", tool: "claude", status: "completed", riskLevel: "low", escalationCount: 0, startedAt: "2024-01-01T00:00:00Z", lastActivityAt: "2024-01-01T01:00:00Z", ciSnapshot: null },
  { id: "sess-002", tool: "claude", status: "active", riskLevel: "high", escalationCount: 2, startedAt: "2024-01-02T00:00:00Z", lastActivityAt: "2024-01-02T01:00:00Z", ciSnapshot: null },
];

const mockPrompts = [
  { id: "p-001", sessionId: "sess-001", type: "yes_no", decision: "auto", confidence: 0.95, actionTaken: "inject_yes", content: "Continue? [y/n]", timestamp: "2024-01-01T00:10:00Z", riskLevel: "low" },
  { id: "p-002", sessionId: "sess-001", type: "yes_no", decision: "escalated", confidence: 0.45, actionTaken: "escalate", content: "Delete all files? [y/n]", timestamp: "2024-01-01T00:20:00Z", riskLevel: "high" },
  { id: "p-003", sessionId: "sess-002", type: "yes_no", decision: "auto", confidence: 0.90, actionTaken: "inject_yes", content: "Proceed? [y/n]", timestamp: "2024-01-02T00:10:00Z", riskLevel: "low" },
];

const mockTraces = [
  { id: "t-001", sessionId: "sess-001", ruleMatched: "allow_yes_no_high_confidence", action: "auto", confidence: "high", timestamp: "2024-01-01T00:10:00Z", hash: "abc123", prompt: "Continue?" },
  { id: "t-002", sessionId: "sess-001", ruleMatched: "default", action: "escalated", confidence: "low", timestamp: "2024-01-01T00:20:00Z", hash: "def456", prompt: "Delete all files?" },
  { id: "t-003", sessionId: "sess-002", ruleMatched: "allow_yes_no_high_confidence", action: "require_human", confidence: "high", timestamp: "2024-01-02T00:10:00Z", hash: "ghi789", prompt: "Proceed?" },
];

const mockAuditEvents = [
  { id: "a-001", sessionId: "sess-001", message: "Prompt auto-approved", actionTaken: "auto", riskLevel: "low", timestamp: "2024-01-01T00:10:00Z", hash: "aaa111" },
  { id: "a-002", sessionId: "sess-001", message: "Escalated to human", actionTaken: "escalated", riskLevel: "high", timestamp: "2024-01-01T00:20:00Z", hash: "bbb222" },
];

const mockIntegrity = {
  overallStatus: "Verified",
  lastVerifiedAt: "2024-01-02T12:00:00Z",
  results: [
    { component: "audit_log", status: "Verified", hash: "ccc333", lastChecked: "2024-01-02T12:00:00Z", details: "Hash chain intact" },
    { component: "decision_trace", status: "Verified", hash: "ddd444", lastChecked: "2024-01-02T12:00:00Z", details: "All entries verified" },
  ],
};

beforeEach(() => {
  vi.mocked(repo.listSessions).mockReturnValue(mockSessions as any);
  vi.mocked(repo.listPrompts).mockReturnValue(mockPrompts as any);
  vi.mocked(repo.listTraces).mockReturnValue(mockTraces as any);
  vi.mocked(repo.listAuditEvents).mockReturnValue(mockAuditEvents as any);
  vi.mocked(repo.getIntegrity).mockReturnValue(mockIntegrity as any);
});

// ---------------------------------------------------------------------------
// redactSecrets
// ---------------------------------------------------------------------------

describe("redactSecrets", () => {
  it("redacts sk- API keys", () => {
    expect(redactSecrets("token: sk-abc123DEF456ghi789JKL012")).toContain("[REDACTED]");
  });

  it("redacts Bearer tokens", () => {
    expect(redactSecrets("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc")).toContain("[REDACTED]");
  });

  it("redacts GitHub PATs", () => {
    expect(redactSecrets("ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890")).toContain("[REDACTED]");
  });

  it("redacts Slack tokens", () => {
    // Construct at runtime to avoid static secret scanner false positives
    const slackToken = ["xoxb", "123456789", "abcdefghijklmnop"].join("-");
    expect(redactSecrets(slackToken)).toContain("[REDACTED]");
  });

  it("redacts password= patterns", () => {
    expect(redactSecrets("password=supersecret123")).toContain("[REDACTED]");
  });

  it("leaves clean text untouched", () => {
    const clean = "This is a normal log message with no secrets.";
    expect(redactSecrets(clean)).toBe(clean);
  });
});

// ---------------------------------------------------------------------------
// computeGovernanceScore
// ---------------------------------------------------------------------------

describe("computeGovernanceScore", () => {
  it("returns a score with all required fields", () => {
    const score = computeGovernanceScore();
    expect(score).toHaveProperty("overall");
    expect(score).toHaveProperty("autonomousRate");
    expect(score).toHaveProperty("escalationRate");
    expect(score).toHaveProperty("blockedHighRisk");
    expect(score).toHaveProperty("policyCoverage");
    expect(score).toHaveProperty("sessionCount");
    expect(score).toHaveProperty("decisionCount");
    expect(score).toHaveProperty("computedAt");
  });

  it("overall score is between 0 and 100", () => {
    const score = computeGovernanceScore();
    expect(score.overall).toBeGreaterThanOrEqual(0);
    expect(score.overall).toBeLessThanOrEqual(100);
  });

  it("counts sessions and decisions correctly", () => {
    const score = computeGovernanceScore();
    expect(score.sessionCount).toBe(2);
    expect(score.decisionCount).toBe(3);
  });

  it("computes autonomous rate correctly", () => {
    // 2 out of 3 prompts are "auto"
    const score = computeGovernanceScore();
    expect(score.autonomousRate).toBeCloseTo(66.7, 0);
  });

  it("filters by sessionId when provided", () => {
    const score = computeGovernanceScore("sess-001");
    expect(score.sessionCount).toBe(1);
    expect(score.decisionCount).toBe(2);
  });

  it("returns zero scores for unknown sessionId", () => {
    const score = computeGovernanceScore("sess-nonexistent");
    expect(score.decisionCount).toBe(0);
    expect(score.sessionCount).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// generateEvidenceJSON
// ---------------------------------------------------------------------------

describe("generateEvidenceJSON", () => {
  it("returns a bundle with required top-level fields", () => {
    const bundle = generateEvidenceJSON();
    expect(bundle).toHaveProperty("generatedAt");
    expect(bundle).toHaveProperty("decisions");
    expect(bundle).toHaveProperty("escalations");
    expect(bundle).toHaveProperty("integrityReport");
    expect(bundle).toHaveProperty("replayReferences");
    expect(bundle).toHaveProperty("policySnapshot");
    expect(bundle).toHaveProperty("governanceScore");
  });

  it("includes decisions for all prompts", () => {
    const bundle = generateEvidenceJSON();
    expect(bundle.decisions).toHaveLength(3);
  });

  it("includes only escalated audit events as escalations", () => {
    const bundle = generateEvidenceJSON();
    expect(bundle.escalations).toHaveLength(1);
    expect(bundle.escalations[0].actionTaken).toBe("escalated");
  });

  it("redacts secrets in decision content", () => {
    vi.mocked(repo.listPrompts).mockReturnValue([
      { ...mockPrompts[0], content: "token=sk-secret123XYZabc456DEF" } as any,
    ]);
    const bundle = generateEvidenceJSON();
    expect(bundle.decisions[0].content).toContain("[REDACTED]");
    expect(bundle.decisions[0].content).not.toContain("sk-secret");
  });

  it("filters to session when sessionId provided", () => {
    const bundle = generateEvidenceJSON("sess-001");
    expect(bundle.decisions).toHaveLength(2);
    expect(bundle.decisions.every(d => d.sessionId === "sess-001")).toBe(true);
  });

  it("integrity report reflects overall status", () => {
    const bundle = generateEvidenceJSON();
    expect(bundle.integrityReport.overallStatus).toBe("Verified");
    expect(bundle.integrityReport.hashChainValid).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// generateEvidenceCSV
// ---------------------------------------------------------------------------

describe("generateEvidenceCSV", () => {
  it("returns a string starting with the header row", () => {
    const csv = generateEvidenceCSV();
    expect(csv.startsWith("type,id,timestamp")).toBe(true);
  });

  it("includes decision rows", () => {
    const csv = generateEvidenceCSV();
    expect(csv).toContain("decision,p-001");
  });

  it("includes escalation rows", () => {
    const csv = generateEvidenceCSV();
    expect(csv).toContain("escalation,a-002");
  });

  it("escapes double quotes in content", () => {
    vi.mocked(repo.listPrompts).mockReturnValue([
      { ...mockPrompts[0], content: 'Say "hello"' } as any,
    ]);
    vi.mocked(repo.listAuditEvents).mockReturnValue([]);
    const csv = generateEvidenceCSV();
    expect(csv).toContain('""hello""');
  });
});

// ---------------------------------------------------------------------------
// generateEvidenceManifest
// ---------------------------------------------------------------------------

describe("generateEvidenceManifest", () => {
  it("includes manifest fields", () => {
    const bundle = generateEvidenceJSON();
    const csv = generateEvidenceCSV();
    const manifest = generateEvidenceManifest(bundle, csv);
    expect(manifest).toHaveProperty("version");
    expect(manifest).toHaveProperty("generatedAt");
    expect(manifest).toHaveProperty("files");
    expect(manifest).toHaveProperty("disclaimer");
  });

  it("includes all expected files in manifest", () => {
    const bundle = generateEvidenceJSON();
    const csv = generateEvidenceCSV();
    const manifest = generateEvidenceManifest(bundle, csv);
    const filenames = manifest.files.map(f => f.filename);
    expect(filenames).toContain("evidence.json");
    expect(filenames).toContain("decisions.csv");
    expect(filenames).toContain("integrity_report.json");
    expect(filenames).toContain("README.txt");
  });

  it("every file has a non-empty sha256 hash", () => {
    const bundle = generateEvidenceJSON();
    const csv = generateEvidenceCSV();
    const manifest = generateEvidenceManifest(bundle, csv);
    for (const file of manifest.files) {
      expect(file.sha256).toMatch(/^[a-f0-9]{64}$/);
    }
  });

  it("disclaimer explicitly disclaims certification", () => {
    const bundle = generateEvidenceJSON();
    const csv = generateEvidenceCSV();
    const manifest = generateEvidenceManifest(bundle, csv);
    const lower = manifest.disclaimer.toLowerCase();
    // Must not positively claim compliance — "does not certify" is fine, "is certified" is not
    expect(lower).not.toMatch(/\bis certified\b/);
    expect(lower).not.toMatch(/\bguarantees compliance\b/);
    // Must contain explicit disclaimer
    expect(lower).toContain("does not certify");
  });
});

// ---------------------------------------------------------------------------
// generateFullBundle
// ---------------------------------------------------------------------------

describe("generateFullBundle", () => {
  it("returns all bundle components", () => {
    const result = generateFullBundle();
    expect(result).toHaveProperty("evidence");
    expect(result).toHaveProperty("csv");
    expect(result).toHaveProperty("integrityReport");
    expect(result).toHaveProperty("manifest");
    expect(result).toHaveProperty("readme");
  });

  it("readme contains the disclaimer", () => {
    const result = generateFullBundle();
    expect(result.readme.toLowerCase()).toContain("does not certify");
  });
});

// ---------------------------------------------------------------------------
// compliancePacks
// ---------------------------------------------------------------------------

describe("compliancePacks", () => {
  it("has four packs", () => {
    expect(compliancePacks).toHaveLength(4);
  });

  it("every pack has a disclaimer", () => {
    for (const pack of compliancePacks) {
      expect(pack.disclaimer).toBeTruthy();
      expect(pack.disclaimer.length).toBeGreaterThan(0);
    }
  });

  it("no pack claims to certify compliance", () => {
    for (const pack of compliancePacks) {
      const lower = (pack.disclaimer + pack.description).toLowerCase();
      expect(lower).not.toContain("certifies");
      expect(lower).not.toContain("is compliant");
    }
  });

  it("every pack has at least one policy", () => {
    for (const pack of compliancePacks) {
      expect(pack.policies.length).toBeGreaterThan(0);
    }
  });

  it("pack action values are valid", () => {
    const validActions = ["enforce", "require_human", "advisory"];
    for (const pack of compliancePacks) {
      for (const policy of pack.policies) {
        expect(validActions).toContain(policy.action);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// bundle list tracking
// ---------------------------------------------------------------------------

describe("bundle list tracking", () => {
  it("starts empty (or accumulates across test runs)", () => {
    const bundles = listGeneratedBundles();
    expect(Array.isArray(bundles)).toBe(true);
  });

  it("addGeneratedBundle returns an entry with an id", () => {
    const entry = addGeneratedBundle({
      generatedAt: new Date().toISOString(),
      format: "bundle",
      decisionCount: 3,
      escalationCount: 1,
      integrityStatus: "Verified",
      governanceScore: 82,
      manifestHash: "abc123",
    });
    expect(entry.id).toMatch(/^evb-/);
    expect(entry.decisionCount).toBe(3);
  });

  it("added bundle appears in listGeneratedBundles", () => {
    const before = listGeneratedBundles().length;
    addGeneratedBundle({
      generatedAt: new Date().toISOString(),
      format: "json",
      decisionCount: 1,
      escalationCount: 0,
      integrityStatus: "Verified",
      governanceScore: 75,
    });
    expect(listGeneratedBundles().length).toBe(before + 1);
  });
});
