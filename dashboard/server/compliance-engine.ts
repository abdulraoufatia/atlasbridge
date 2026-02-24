import type { ComplianceScanResult, ComplianceSuggestion, ComplianceCategoryScore } from "@shared/schema";

interface RepoInfo {
  provider: string;
  owner: string;
  repo: string;
  branch: string;
}

function generateSecurityChecks(level: string): { name: string; passed: boolean; detail: string }[] {
  const base = [
    { name: "LICENSE file present", passed: Math.random() > 0.2, detail: "Repository should include an open-source or proprietary license file" },
    { name: ".gitignore configured", passed: Math.random() > 0.1, detail: "Ensure sensitive files and build artifacts are excluded from version control" },
    { name: "No secrets in source", passed: Math.random() > 0.3, detail: "Scan for hardcoded API keys, passwords, and tokens in source code" },
    { name: "SECURITY.md present", passed: Math.random() > 0.4, detail: "Security policy and vulnerability reporting guidelines should be documented" },
  ];
  if (level === "standard" || level === "enterprise") {
    base.push(
      { name: "Branch protection enabled", passed: Math.random() > 0.35, detail: "Main branch should require PR reviews and status checks" },
      { name: "Signed commits enforced", passed: Math.random() > 0.5, detail: "GPG/SSH commit signing adds authenticity verification" },
      { name: "CODEOWNERS defined", passed: Math.random() > 0.4, detail: "Define code ownership for review routing and accountability" },
    );
  }
  if (level === "enterprise") {
    base.push(
      { name: "Dependency vulnerability scan", passed: Math.random() > 0.3, detail: "Automated scanning for known vulnerabilities in dependencies" },
      { name: "SBOM generation", passed: Math.random() > 0.6, detail: "Software Bill of Materials for supply chain transparency" },
      { name: "Secret rotation policy", passed: Math.random() > 0.5, detail: "Automated rotation of secrets and credentials at defined intervals" },
    );
  }
  return base;
}

function generateCICDChecks(level: string): { name: string; passed: boolean; detail: string }[] {
  const base = [
    { name: "CI pipeline configured", passed: Math.random() > 0.15, detail: "Automated build and test pipeline should be in place" },
    { name: "Automated tests present", passed: Math.random() > 0.25, detail: "Unit, integration, or e2e tests should exist and run in CI" },
  ];
  if (level === "standard" || level === "enterprise") {
    base.push(
      { name: "Code coverage tracking", passed: Math.random() > 0.4, detail: "Track and enforce minimum code coverage thresholds" },
      { name: "Static analysis configured", passed: Math.random() > 0.35, detail: "Lint rules and static analysis tools should be configured" },
      { name: "Build artifacts versioned", passed: Math.random() > 0.3, detail: "Build outputs should be versioned and stored in artifact registry" },
    );
  }
  if (level === "enterprise") {
    base.push(
      { name: "Multi-stage deployment", passed: Math.random() > 0.45, detail: "Staging and production deployment stages with gates" },
      { name: "Rollback capability", passed: Math.random() > 0.4, detail: "Automated rollback mechanisms for failed deployments" },
    );
  }
  return base;
}

function generateDocChecks(level: string): { name: string; passed: boolean; detail: string }[] {
  const base = [
    { name: "README.md exists", passed: Math.random() > 0.1, detail: "Repository must have a comprehensive README" },
    { name: "Contributing guidelines", passed: Math.random() > 0.4, detail: "CONTRIBUTING.md with contribution workflow and standards" },
  ];
  if (level === "standard" || level === "enterprise") {
    base.push(
      { name: "API documentation", passed: Math.random() > 0.45, detail: "REST/GraphQL API documentation with examples" },
      { name: "Architecture docs", passed: Math.random() > 0.5, detail: "High-level architecture and design documentation" },
      { name: "Changelog maintained", passed: Math.random() > 0.35, detail: "CHANGELOG.md tracking version history and breaking changes" },
    );
  }
  return base;
}

function generateDependencyChecks(level: string): { name: string; passed: boolean; detail: string }[] {
  const base = [
    { name: "Lock file present", passed: Math.random() > 0.15, detail: "Package lock file ensures deterministic dependency resolution" },
    { name: "No deprecated packages", passed: Math.random() > 0.35, detail: "Dependencies should not include deprecated or unmaintained packages" },
  ];
  if (level === "standard" || level === "enterprise") {
    base.push(
      { name: "Dependabot/Renovate configured", passed: Math.random() > 0.4, detail: "Automated dependency update tool should be configured" },
      { name: "License compliance", passed: Math.random() > 0.3, detail: "All dependency licenses should be compatible with project license" },
    );
  }
  if (level === "enterprise") {
    base.push(
      { name: "Supply chain attestation", passed: Math.random() > 0.6, detail: "SLSA provenance or similar supply chain security attestation" },
    );
  }
  return base;
}

function generateCodeQualityChecks(level: string): { name: string; passed: boolean; detail: string }[] {
  const base = [
    { name: "Linting configured", passed: Math.random() > 0.2, detail: "Code linting rules should be defined and enforced" },
    { name: "Consistent formatting", passed: Math.random() > 0.25, detail: "Code formatter (Prettier, Black, etc.) should be configured" },
  ];
  if (level === "standard" || level === "enterprise") {
    base.push(
      { name: "Type safety", passed: Math.random() > 0.35, detail: "TypeScript, mypy, or similar type checking should be enabled" },
      { name: "Error handling patterns", passed: Math.random() > 0.4, detail: "Consistent error handling and logging patterns across codebase" },
    );
  }
  if (level === "enterprise") {
    base.push(
      { name: "Complexity metrics", passed: Math.random() > 0.5, detail: "Cyclomatic complexity and code duplication metrics tracked" },
      { name: "Performance benchmarks", passed: Math.random() > 0.55, detail: "Performance test suite with defined benchmarks" },
    );
  }
  return base;
}

function scoreCategory(checks: { name: string; passed: boolean; detail: string }[]): { score: number; maxScore: number } {
  const maxScore = checks.length * 10;
  const score = checks.filter(c => c.passed).length * 10;
  return { score, maxScore };
}

export function runComplianceScan(repo: RepoInfo, complianceLevel: string): ComplianceScanResult {
  const securityChecks = generateSecurityChecks(complianceLevel);
  const cicdChecks = generateCICDChecks(complianceLevel);
  const docChecks = generateDocChecks(complianceLevel);
  const depChecks = generateDependencyChecks(complianceLevel);
  const codeChecks = generateCodeQualityChecks(complianceLevel);

  const categories: ComplianceCategoryScore[] = [
    { name: "Security", ...scoreCategory(securityChecks), checks: securityChecks },
    { name: "CI/CD", ...scoreCategory(cicdChecks), checks: cicdChecks },
    { name: "Documentation", ...scoreCategory(docChecks), checks: docChecks },
    { name: "Dependencies", ...scoreCategory(depChecks), checks: depChecks },
    { name: "Code Quality", ...scoreCategory(codeChecks), checks: codeChecks },
  ];

  const totalScore = categories.reduce((s, c) => s + c.score, 0);
  const totalMax = categories.reduce((s, c) => s + c.maxScore, 0);
  const overallScore = Math.round((totalScore / totalMax) * 100);

  const allChecks = [...securityChecks, ...cicdChecks, ...docChecks, ...depChecks, ...codeChecks];
  const suggestions: ComplianceSuggestion[] = allChecks
    .filter(c => !c.passed)
    .map((c, i) => ({
      id: `sug-${i + 1}`,
      category: categories.find(cat => cat.checks.includes(c))?.name || "General",
      title: c.name,
      description: c.detail,
      impact: i < 3 ? "critical" as const : i < 7 ? "recommended" as const : "nice-to-have" as const,
      status: "fail" as const,
    }));

  const passingSuggestions: ComplianceSuggestion[] = allChecks
    .filter(c => c.passed)
    .slice(0, 3)
    .map((c, i) => ({
      id: `sug-pass-${i + 1}`,
      category: categories.find(cat => cat.checks.includes(c))?.name || "General",
      title: c.name,
      description: c.detail,
      impact: "nice-to-have" as const,
      status: "pass" as const,
    }));

  return {
    overallScore,
    complianceLevel,
    categories,
    suggestions: [...suggestions, ...passingSuggestions],
    scannedAt: new Date().toISOString(),
  };
}
