import type { QualityScanResult, QualityCategoryScore, QualitySuggestion } from "@shared/schema";
import type { RepoContext, RepoSnapshot, ProviderClient } from "./types";
import type { Check } from "./evaluator";
import { GitHubClient } from "./github";
import { GitLabClient } from "./gitlab";
import { BitbucketClient } from "./bitbucket";
import { AzureDevOpsClient } from "./azure-devops";
import { evaluateChecks } from "./evaluator";

const clients: Record<string, ProviderClient> = {
  github: new GitHubClient(),
  gitlab: new GitLabClient(),
  bitbucket: new BitbucketClient(),
  azure: new AzureDevOpsClient(),
};

/** All file paths to probe across all categories. */
const ALL_PATHS = [
  // Security
  "LICENSE", "LICENSE.md", "LICENSE.txt", ".gitignore", "SECURITY.md",
  "CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS",
  // CI/CD
  ".github/workflows", ".gitlab-ci.yml", "bitbucket-pipelines.yml", "azure-pipelines.yml",
  // Tests
  "jest.config.js", "jest.config.ts", "jest.config.mjs",
  "vitest.config.ts", "vitest.config.js",
  "pytest.ini", "setup.cfg", "tox.ini", "Cargo.toml",
  // Coverage
  ".coveragerc", ".nycrc", ".nycrc.json", "codecov.yml", ".codecov.yml",
  // Static analysis
  ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml",
  "ruff.toml", ".flake8", "pylintrc", ".pylintrc",
  // Documentation
  "README.md", "readme.md", "README",
  "CONTRIBUTING.md", "contributing.md", ".github/CONTRIBUTING.md",
  "CHANGELOG.md", "changelog.md", "CHANGES.md", "HISTORY.md",
  "docs/api.md", "docs/API.md", "openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json",
  "docs/architecture.md", "docs/ARCHITECTURE.md", "ARCHITECTURE.md", "docs/design.md",
  // Dependencies
  "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
  "Pipfile.lock", "poetry.lock", "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock",
  ".github/dependabot.yml", ".github/dependabot.yaml",
  "renovate.json", ".renovaterc", ".renovaterc.json",
  // Code quality
  ".prettierrc", ".prettierrc.js", ".prettierrc.json", ".prettierrc.yml",
  ".editorconfig", "biome.json", "rustfmt.toml",
  "tsconfig.json", "mypy.ini", "pyrightconfig.json", "pyproject.toml",
  // Benchmarks
  "bench", "benchmarks", "__benchmarks__",
];

function scoreCategory(checks: Check[]): { score: number; maxScore: number } {
  const maxScore = checks.length * 10;
  const score = checks.filter((c) => c.passed).length * 10;
  return { score, maxScore };
}

function buildResult(
  checks: ReturnType<typeof evaluateChecks>,
  qualityLevel: string,
): QualityScanResult {
  const categories: QualityCategoryScore[] = [
    { name: "Security", ...scoreCategory(checks.security), checks: checks.security },
    { name: "CI/CD", ...scoreCategory(checks.cicd), checks: checks.cicd },
    { name: "Documentation", ...scoreCategory(checks.documentation), checks: checks.documentation },
    { name: "Dependencies", ...scoreCategory(checks.dependencies), checks: checks.dependencies },
    { name: "Code Quality", ...scoreCategory(checks.codeQuality), checks: checks.codeQuality },
  ];

  const totalScore = categories.reduce((s, c) => s + c.score, 0);
  const totalMax = categories.reduce((s, c) => s + c.maxScore, 0);
  const overallScore = totalMax > 0 ? Math.round((totalScore / totalMax) * 100) : 0;

  const allChecks = [
    ...checks.security, ...checks.cicd, ...checks.documentation,
    ...checks.dependencies, ...checks.codeQuality,
  ];

  const suggestions: QualitySuggestion[] = allChecks
    .filter((c) => !c.passed)
    .map((c, i) => ({
      id: `sug-${i + 1}`,
      category: categories.find((cat) => cat.checks.includes(c))?.name ?? "General",
      title: c.name,
      description: c.detail,
      impact: (i < 3 ? "critical" : i < 7 ? "recommended" : "nice-to-have") as QualitySuggestion["impact"],
      status: "fail" as const,
      details: c.remediation,
    }));

  const passingSuggestions: QualitySuggestion[] = allChecks
    .filter((c) => c.passed)
    .slice(0, 3)
    .map((c, i) => ({
      id: `sug-pass-${i + 1}`,
      category: categories.find((cat) => cat.checks.includes(c))?.name ?? "General",
      title: c.name,
      description: c.detail,
      impact: "nice-to-have" as const,
      status: "pass" as const,
      details: c.remediation,
    }));

  return {
    overallScore,
    qualityLevel,
    categories,
    suggestions: [...suggestions, ...passingSuggestions],
    scannedAt: new Date().toISOString(),
  };
}

export async function runQualityScan(
  repo: { provider: string; owner: string; repo: string; branch: string },
  qualityLevel: string,
  accessToken?: string | null,
): Promise<QualityScanResult> {
  const ctx: RepoContext = { ...repo, accessToken };
  const client = clients[repo.provider];
  if (!client) throw new Error(`Unsupported provider: ${repo.provider}`);

  const [filesResult, protectionResult, metadataResult] = await Promise.allSettled([
    client.checkFiles(ctx, ALL_PATHS),
    client.checkBranchProtection(ctx),
    client.getMetadata(ctx),
  ]);

  const snapshot: RepoSnapshot = {
    files: filesResult.status === "fulfilled" ? filesResult.value : {},
    branchProtection: protectionResult.status === "fulfilled"
      ? protectionResult.value
      : { available: false, requiresPrReviews: null, requiresStatusChecks: null, requiresSignedCommits: null },
    metadata: metadataResult.status === "fulfilled"
      ? metadataResult.value
      : { languages: [], topics: [], defaultBranch: ctx.branch, hasIssues: true },
    errors: [
      ...(filesResult.status === "rejected" ? [`File check failed: ${filesResult.reason}`] : []),
      ...(protectionResult.status === "rejected" ? [`Branch protection check failed: ${protectionResult.reason}`] : []),
      ...(metadataResult.status === "rejected" ? [`Metadata fetch failed: ${metadataResult.reason}`] : []),
    ],
  };

  const checks = evaluateChecks(snapshot, ctx, qualityLevel);
  return buildResult(checks, qualityLevel);
}
