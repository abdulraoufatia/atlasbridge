import { describe, it, expect, vi, beforeEach } from "vitest";
import type { RepoSnapshot, RepoContext } from "../scanner/types";
import { evaluateChecks } from "../scanner/evaluator";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function makeSnapshot(files: Record<string, boolean> = {}, overrides?: Partial<RepoSnapshot>): RepoSnapshot {
  return {
    files,
    branchProtection: { available: false, requiresPrReviews: null, requiresStatusChecks: null, requiresSignedCommits: null },
    metadata: { languages: [], topics: [], defaultBranch: "main", hasIssues: true },
    errors: [],
    ...overrides,
  };
}

const ghCtx: RepoContext = { provider: "github", owner: "test", repo: "repo", branch: "main" };
const glCtx: RepoContext = { provider: "gitlab", owner: "test", repo: "repo", branch: "main" };

// ---------------------------------------------------------------------------
// Evaluator — basic level
// ---------------------------------------------------------------------------
describe("evaluateChecks", () => {
  it("returns all categories", () => {
    const result = evaluateChecks(makeSnapshot(), ghCtx, "basic");
    expect(result).toHaveProperty("security");
    expect(result).toHaveProperty("cicd");
    expect(result).toHaveProperty("documentation");
    expect(result).toHaveProperty("dependencies");
    expect(result).toHaveProperty("codeQuality");
  });

  it("basic level produces fewer checks than advanced", () => {
    const basic = evaluateChecks(makeSnapshot(), ghCtx, "basic");
    const advanced = evaluateChecks(makeSnapshot(), ghCtx, "advanced");
    const countChecks = (r: ReturnType<typeof evaluateChecks>) =>
      Object.values(r).reduce((s, arr) => s + arr.length, 0);
    expect(countChecks(advanced)).toBeGreaterThan(countChecks(basic));
  });

  it("empty snapshot produces all-fail for file-based checks", () => {
    const result = evaluateChecks(makeSnapshot(), ghCtx, "basic");
    expect(result.security.find((c) => c.name === "LICENSE file present")?.passed).toBe(false);
    expect(result.security.find((c) => c.name === ".gitignore configured")?.passed).toBe(false);
    expect(result.documentation.find((c) => c.name === "README.md exists")?.passed).toBe(false);
  });

  it("LICENSE present passes the check", () => {
    const result = evaluateChecks(makeSnapshot({ "LICENSE": true }), ghCtx, "basic");
    expect(result.security.find((c) => c.name === "LICENSE file present")?.passed).toBe(true);
  });

  it("LICENSE.md also passes", () => {
    const result = evaluateChecks(makeSnapshot({ "LICENSE.md": true }), ghCtx, "basic");
    expect(result.security.find((c) => c.name === "LICENSE file present")?.passed).toBe(true);
  });

  it("README check works", () => {
    const result = evaluateChecks(makeSnapshot({ "README.md": true }), ghCtx, "basic");
    expect(result.documentation.find((c) => c.name === "README.md exists")?.passed).toBe(true);
  });

  it(".gitignore check works", () => {
    const result = evaluateChecks(makeSnapshot({ ".gitignore": true }), ghCtx, "basic");
    expect(result.security.find((c) => c.name === ".gitignore configured")?.passed).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// CI/CD checks — provider-specific
// ---------------------------------------------------------------------------
describe("CI/CD provider-specific checks", () => {
  it("GitHub: .github/workflows passes CI check", () => {
    const result = evaluateChecks(makeSnapshot({ ".github/workflows": true }), ghCtx, "basic");
    expect(result.cicd.find((c) => c.name === "CI pipeline configured")?.passed).toBe(true);
  });

  it("GitLab: .gitlab-ci.yml passes CI check", () => {
    const result = evaluateChecks(makeSnapshot({ ".gitlab-ci.yml": true }), glCtx, "basic");
    expect(result.cicd.find((c) => c.name === "CI pipeline configured")?.passed).toBe(true);
  });

  it("GitHub: .gitlab-ci.yml does NOT pass CI check", () => {
    const result = evaluateChecks(makeSnapshot({ ".gitlab-ci.yml": true }), ghCtx, "basic");
    expect(result.cicd.find((c) => c.name === "CI pipeline configured")?.passed).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Branch protection checks
// ---------------------------------------------------------------------------
describe("branch protection checks", () => {
  it("PR review required passes when protection available", () => {
    const snapshot = makeSnapshot({}, {
      branchProtection: { available: true, requiresPrReviews: true, requiresStatusChecks: true, requiresSignedCommits: false },
    });
    const result = evaluateChecks(snapshot, ghCtx, "standard");
    expect(result.security.find((c) => c.name === "Branch protection enabled")?.passed).toBe(true);
  });

  it("detail explains when protection is unavailable", () => {
    const result = evaluateChecks(makeSnapshot(), ghCtx, "standard");
    const check = result.security.find((c) => c.name === "Branch protection enabled");
    expect(check?.passed).toBe(false);
    expect(check?.detail).toContain("requires admin token");
  });

  it("signed commits check", () => {
    const snapshot = makeSnapshot({}, {
      branchProtection: { available: true, requiresPrReviews: false, requiresStatusChecks: false, requiresSignedCommits: true },
    });
    const result = evaluateChecks(snapshot, ghCtx, "standard");
    expect(result.security.find((c) => c.name === "Signed commits enforced")?.passed).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Dependency checks
// ---------------------------------------------------------------------------
describe("dependency checks", () => {
  it("package-lock.json passes lock file check", () => {
    const result = evaluateChecks(makeSnapshot({ "package-lock.json": true }), ghCtx, "basic");
    expect(result.dependencies.find((c) => c.name === "Lock file present")?.passed).toBe(true);
  });

  it("poetry.lock passes lock file check", () => {
    const result = evaluateChecks(makeSnapshot({ "poetry.lock": true }), ghCtx, "basic");
    expect(result.dependencies.find((c) => c.name === "Lock file present")?.passed).toBe(true);
  });

  it("dependabot config passes at standard level", () => {
    const result = evaluateChecks(makeSnapshot({ ".github/dependabot.yml": true }), ghCtx, "standard");
    expect(result.dependencies.find((c) => c.name === "Dependabot/Renovate configured")?.passed).toBe(true);
  });

  it("renovate.json also passes", () => {
    const result = evaluateChecks(makeSnapshot({ "renovate.json": true }), ghCtx, "standard");
    expect(result.dependencies.find((c) => c.name === "Dependabot/Renovate configured")?.passed).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Code quality checks
// ---------------------------------------------------------------------------
describe("code quality checks", () => {
  it("eslint config passes linting check", () => {
    const result = evaluateChecks(makeSnapshot({ ".eslintrc.json": true }), ghCtx, "basic");
    expect(result.codeQuality.find((c) => c.name === "Linting configured")?.passed).toBe(true);
  });

  it("ruff.toml passes linting check", () => {
    const result = evaluateChecks(makeSnapshot({ "ruff.toml": true }), ghCtx, "basic");
    expect(result.codeQuality.find((c) => c.name === "Linting configured")?.passed).toBe(true);
  });

  it("prettier config passes formatting check", () => {
    const result = evaluateChecks(makeSnapshot({ ".prettierrc": true }), ghCtx, "basic");
    expect(result.codeQuality.find((c) => c.name === "Consistent formatting")?.passed).toBe(true);
  });

  it("tsconfig.json passes type safety check at standard level", () => {
    const result = evaluateChecks(makeSnapshot({ "tsconfig.json": true }), ghCtx, "standard");
    expect(result.codeQuality.find((c) => c.name === "Type safety")?.passed).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Full snapshot — high score
// ---------------------------------------------------------------------------
describe("full snapshot scoring", () => {
  it("well-configured repo gets high scores across all categories", () => {
    const files: Record<string, boolean> = {
      "LICENSE": true, ".gitignore": true, "SECURITY.md": true,
      "CODEOWNERS": true, ".github/dependabot.yml": true,
      ".github/workflows": true, "jest.config.ts": true,
      ".coveragerc": true, ".eslintrc.json": true,
      "README.md": true, "CONTRIBUTING.md": true,
      "CHANGELOG.md": true, "docs/architecture.md": true, "docs/api.md": true,
      "package-lock.json": true, "renovate.json": true,
      ".prettierrc": true, "tsconfig.json": true,
    };
    const snapshot = makeSnapshot(files, {
      branchProtection: { available: true, requiresPrReviews: true, requiresStatusChecks: true, requiresSignedCommits: true },
    });
    const result = evaluateChecks(snapshot, ghCtx, "standard");

    // Every file-based check in standard level should pass
    for (const category of Object.values(result)) {
      for (const check of category) {
        if (check.detail.includes("Cannot verify") || check.detail.includes("Requires") || check.detail.includes("not verifiable")) continue;
        if (check.detail.includes("assumed")) continue;
        expect(check.passed).toBe(true);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// runQualityScan orchestrator (mocked providers)
// ---------------------------------------------------------------------------
describe("runQualityScan", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns valid QualityScanResult shape", async () => {
    // Mock fetch globally to simulate GitHub API
    const mockFetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/git/trees/")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            tree: [
              { path: "LICENSE", type: "blob" },
              { path: "README.md", type: "blob" },
              { path: ".gitignore", type: "blob" },
            ],
            truncated: false,
          }),
        });
      }
      if (url.includes("/protection")) {
        return Promise.resolve({ ok: false, status: 404 });
      }
      if (url.includes("/repos/") && !url.includes("/languages")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ language: "TypeScript", topics: [], default_branch: "main", has_issues: true }),
        });
      }
      if (url.includes("/languages")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ TypeScript: 10000, JavaScript: 5000 }),
        });
      }
      return Promise.resolve({ ok: false, status: 404 });
    });
    vi.stubGlobal("fetch", mockFetch);

    const { runQualityScan } = await import("../scanner/index");
    const result = await runQualityScan(
      { provider: "github", owner: "test", repo: "repo", branch: "main" },
      "basic",
      null,
    );

    expect(result).toHaveProperty("overallScore");
    expect(result).toHaveProperty("qualityLevel", "basic");
    expect(result).toHaveProperty("categories");
    expect(result).toHaveProperty("suggestions");
    expect(result).toHaveProperty("scannedAt");
    expect(result.overallScore).toBeGreaterThanOrEqual(0);
    expect(result.overallScore).toBeLessThanOrEqual(100);
    expect(result.categories).toHaveLength(5);

    // LICENSE and README should pass, .gitignore should pass
    const securityCat = result.categories.find((c) => c.name === "Security");
    expect(securityCat?.checks.find((c) => c.name === "LICENSE file present")?.passed).toBe(true);
    expect(securityCat?.checks.find((c) => c.name === ".gitignore configured")?.passed).toBe(true);

    vi.unstubAllGlobals();
  });

  it("throws on unsupported provider", async () => {
    const { runQualityScan } = await import("../scanner/index");
    await expect(
      runQualityScan({ provider: "unknown", owner: "o", repo: "r", branch: "main" }, "basic"),
    ).rejects.toThrow("Unsupported provider");
  });

  it("handles API failures gracefully with partial results", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("Network error"));
    vi.stubGlobal("fetch", mockFetch);

    const { runQualityScan } = await import("../scanner/index");
    const result = await runQualityScan(
      { provider: "github", owner: "test", repo: "repo", branch: "main" },
      "basic",
      null,
    );

    // Should still return a valid result — all checks fail but no crash
    expect(result).toHaveProperty("overallScore");
    expect(result.categories).toHaveLength(5);

    vi.unstubAllGlobals();
  });
});
