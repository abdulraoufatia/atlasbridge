import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import path from "path";
import fs from "fs";
import os from "os";

// ---------------------------------------------------------------------------
// Patterns tests
// ---------------------------------------------------------------------------
describe("patterns", () => {
  it("SENSITIVE_PATH_PATTERNS match expected files", async () => {
    const { SENSITIVE_PATH_PATTERNS } = await import("../scanner/patterns");

    const shouldMatch = [".env", ".env.local", "secrets.json", "credentials.yaml", "key.pem"];
    const shouldNotMatch = ["README.md", "src/index.ts", "package.json"];

    for (const file of shouldMatch) {
      const matched = SENSITIVE_PATH_PATTERNS.some((p) => p.pattern.test(file));
      expect(matched, `Expected ${file} to match a sensitive pattern`).toBe(true);
    }

    for (const file of shouldNotMatch) {
      const matched = SENSITIVE_PATH_PATTERNS.some((p) => p.pattern.test(file));
      expect(matched, `Expected ${file} NOT to match a sensitive pattern`).toBe(false);
    }
  });

  it("SECRET_PATTERNS detect known token formats", async () => {
    const { SECRET_PATTERNS } = await import("../scanner/patterns");

    const testCases = [
      { input: "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij", expectedType: "github-pat" },
      { input: "glpat-abcdef1234567890abcde", expectedType: "gitlab-pat" },
      { input: "xoxb-123456789-abcdefgh", expectedType: "slack-token" },
      { input: "AKIAIOSFODNN7EXAMPLE", expectedType: "aws-access-key" },
      { input: "-----BEGIN PRIVATE KEY-----", expectedType: "private-key" },
    ];

    for (const { input, expectedType } of testCases) {
      const matched = SECRET_PATTERNS.find((p) => {
        p.pattern.lastIndex = 0;
        return p.pattern.test(input);
      });
      expect(matched, `Expected "${input}" to match pattern "${expectedType}"`).toBeDefined();
      expect(matched!.name).toBe(expectedType);
    }
  });

  it("LANGUAGE_EXTENSIONS maps common extensions", async () => {
    const { LANGUAGE_EXTENSIONS } = await import("../scanner/patterns");

    expect(LANGUAGE_EXTENSIONS[".ts"]).toBe("TypeScript");
    expect(LANGUAGE_EXTENSIONS[".py"]).toBe("Python");
    expect(LANGUAGE_EXTENSIONS[".rs"]).toBe("Rust");
    expect(LANGUAGE_EXTENSIONS[".go"]).toBe("Go");
  });

  it("BUILD_SYSTEM_FILES maps config files to systems", async () => {
    const { BUILD_SYSTEM_FILES } = await import("../scanner/patterns");

    expect(BUILD_SYSTEM_FILES["package.json"]).toBe("npm");
    expect(BUILD_SYSTEM_FILES["Cargo.toml"]).toBe("cargo");
    expect(BUILD_SYSTEM_FILES["pyproject.toml"]).toBe("pip/poetry");
  });
});

// ---------------------------------------------------------------------------
// Local scanner inventory tests (using temp directory)
// ---------------------------------------------------------------------------
describe("scanInventory", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "atlasbridge-test-"));
    // Initialize a git repo so git ls-files works
    const { execFileSync } = require("child_process");
    execFileSync("git", ["init"], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["config", "user.email", "test@test.com"], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["config", "user.name", "Test"], { cwd: tmpDir, stdio: "pipe" });
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  function writeAndCommit(files: Record<string, string>) {
    const { execFileSync } = require("child_process");
    for (const [filePath, content] of Object.entries(files)) {
      const fullPath = path.join(tmpDir, filePath);
      fs.mkdirSync(path.dirname(fullPath), { recursive: true });
      fs.writeFileSync(fullPath, content);
    }
    execFileSync("git", ["add", "."], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["commit", "-m", "test"], { cwd: tmpDir, stdio: "pipe" });
  }

  it("detects languages from file extensions", async () => {
    writeAndCommit({
      "src/index.ts": "console.log('hello');",
      "src/utils.ts": "export const x = 1;",
      "src/main.py": "print('hello')",
      "README.md": "# Test",
    });

    const { scanInventory } = await import("../scanner/local");
    const inv = scanInventory(tmpDir);

    expect(inv.totalFiles).toBe(4);
    expect(inv.languages.length).toBeGreaterThan(0);
    expect(inv.languages[0].name).toBe("TypeScript");
    expect(inv.languages[0].files).toBe(2);
  });

  it("detects build systems", async () => {
    writeAndCommit({
      "package.json": '{"name": "test"}',
      "src/index.ts": "export default 1;",
    });

    const { scanInventory } = await import("../scanner/local");
    const inv = scanInventory(tmpDir);

    expect(inv.buildSystems).toContain("npm");
  });

  it("detects CI platforms", async () => {
    writeAndCommit({
      ".github/workflows/ci.yml": "name: CI\non: push",
      "src/index.ts": "export default 1;",
    });

    const { scanInventory } = await import("../scanner/local");
    const inv = scanInventory(tmpDir);

    expect(inv.ciPlatforms).toContain("github-actions");
  });

  it("detects frameworks", async () => {
    writeAndCommit({
      "next.config.js": "module.exports = {}",
      "tailwind.config.js": "module.exports = {}",
      "src/index.ts": "export default 1;",
    });

    const { scanInventory } = await import("../scanner/local");
    const inv = scanInventory(tmpDir);

    expect(inv.frameworks).toContain("Next.js");
    expect(inv.frameworks).toContain("Tailwind CSS");
  });
});

// ---------------------------------------------------------------------------
// Safety boundaries tests
// ---------------------------------------------------------------------------
describe("scanSafetyBoundaries", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "atlasbridge-test-"));
    const { execFileSync } = require("child_process");
    execFileSync("git", ["init"], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["config", "user.email", "test@test.com"], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["config", "user.name", "Test"], { cwd: tmpDir, stdio: "pipe" });
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  function writeAndCommit(files: Record<string, string>) {
    const { execFileSync } = require("child_process");
    for (const [filePath, content] of Object.entries(files)) {
      const fullPath = path.join(tmpDir, filePath);
      fs.mkdirSync(path.dirname(fullPath), { recursive: true });
      fs.writeFileSync(fullPath, content);
    }
    execFileSync("git", ["add", "."], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["commit", "-m", "test"], { cwd: tmpDir, stdio: "pipe" });
  }

  it("detects sensitive paths", async () => {
    writeAndCommit({
      ".env": "SECRET=abc",
      ".env.local": "DB_PASS=123",
      "src/index.ts": "export default 1;",
    });

    const { scanSafetyBoundaries } = await import("../scanner/local");
    const sb = scanSafetyBoundaries(tmpDir);

    expect(sb.sensitivePaths.length).toBeGreaterThan(0);
    const envEntry = sb.sensitivePaths.find((p) => p.path === ".env");
    expect(envEntry).toBeDefined();
    expect(envEntry!.risk).toBe("high");
  });

  it("detects tool surfaces", async () => {
    writeAndCommit({
      ".claude/config.json": "{}",
      ".vscode/settings.json": "{}",
      "src/index.ts": "export default 1;",
    });

    const { scanSafetyBoundaries } = await import("../scanner/local");
    const sb = scanSafetyBoundaries(tmpDir);

    expect(sb.toolSurfaces.length).toBeGreaterThan(0);
    expect(sb.toolSurfaces.find((t) => t.tool === "Claude Code")).toBeDefined();
    expect(sb.toolSurfaces.find((t) => t.tool === "VS Code")).toBeDefined();
  });

  it("detects CI safety checks", async () => {
    writeAndCommit({
      ".github/workflows/ci.yml": `
name: CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npx eslint .
      - run: npx tsc --noEmit
      - run: npm test
`,
      "src/index.ts": "export default 1;",
    });

    const { scanSafetyBoundaries } = await import("../scanner/local");
    const sb = scanSafetyBoundaries(tmpDir);

    expect(sb.ciSafetyChecks.length).toBeGreaterThan(0);
    const linting = sb.ciSafetyChecks.find((c) => c.name === "Linting step");
    expect(linting?.present).toBe(true);
    const typeCheck = sb.ciSafetyChecks.find((c) => c.name === "Type checking");
    expect(typeCheck?.present).toBe(true);
    const testing = sb.ciSafetyChecks.find((c) => c.name === "Test execution");
    expect(testing?.present).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Secret scanner tests
// ---------------------------------------------------------------------------
describe("scanForSecrets", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "atlasbridge-test-"));
    const { execFileSync } = require("child_process");
    execFileSync("git", ["init"], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["config", "user.email", "test@test.com"], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["config", "user.name", "Test"], { cwd: tmpDir, stdio: "pipe" });
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  function writeAndCommit(files: Record<string, string>) {
    const { execFileSync } = require("child_process");
    for (const [filePath, content] of Object.entries(files)) {
      const fullPath = path.join(tmpDir, filePath);
      fs.mkdirSync(path.dirname(fullPath), { recursive: true });
      fs.writeFileSync(fullPath, content);
    }
    execFileSync("git", ["add", "."], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["commit", "-m", "test"], { cwd: tmpDir, stdio: "pipe" });
  }

  it("detects GitHub PAT", async () => {
    writeAndCommit({
      "config.js": 'const token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij";',
    });

    const { scanForSecrets } = await import("../scanner/secrets");
    const findings = scanForSecrets(tmpDir);

    expect(findings.length).toBeGreaterThan(0);
    const ghpFinding = findings.find((f) => f.type === "github-pat");
    expect(ghpFinding).toBeDefined();
    expect(ghpFinding!.file).toBe("config.js");
    expect(ghpFinding!.line).toBe(1);
    // Fingerprint should be a 12-char hex string
    expect(ghpFinding!.fingerprint).toMatch(/^[a-f0-9]{12}$/);
  });

  it("detects AWS access key", async () => {
    writeAndCommit({
      "deploy.sh": "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
    });

    const { scanForSecrets } = await import("../scanner/secrets");
    const findings = scanForSecrets(tmpDir);

    const awsFinding = findings.find((f) => f.type === "aws-access-key");
    expect(awsFinding).toBeDefined();
  });

  it("skips binary files", async () => {
    writeAndCommit({
      "image.png": "fake binary content with ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh",
    });

    const { scanForSecrets } = await import("../scanner/secrets");
    const findings = scanForSecrets(tmpDir);

    expect(findings.length).toBe(0);
  });

  it("returns empty for clean repo", async () => {
    writeAndCommit({
      "src/index.ts": "console.log('hello world');",
      "package.json": '{"name": "clean-project"}',
    });

    const { scanForSecrets } = await import("../scanner/secrets");
    const findings = scanForSecrets(tmpDir);

    expect(findings.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Dependency scanner tests
// ---------------------------------------------------------------------------
describe("scanDependencies", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "atlasbridge-test-"));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it("parses package-lock.json v2", async () => {
    const lockfile = {
      lockfileVersion: 3,
      packages: {
        "": { name: "test", version: "1.0.0" },
        "node_modules/express": { version: "4.18.2", license: "MIT" },
        "node_modules/lodash": { version: "4.17.21", license: "MIT" },
      },
    };
    fs.writeFileSync(path.join(tmpDir, "package-lock.json"), JSON.stringify(lockfile));

    const { scanDependencies } = await import("../scanner/dependencies");
    const { licenses } = scanDependencies(tmpDir);

    expect(licenses.find((l) => l.name === "express")).toBeDefined();
    expect(licenses.find((l) => l.name === "lodash")).toBeDefined();
  });

  it("detects project license", async () => {
    fs.writeFileSync(path.join(tmpDir, "LICENSE"), "MIT License\n\nCopyright (c) 2024");

    const { scanDependencies } = await import("../scanner/dependencies");
    const { licenses } = scanDependencies(tmpDir);

    const project = licenses.find((l) => l.name === "(project)");
    expect(project).toBeDefined();
    expect(project!.license).toBe("MIT");
    expect(project!.risk).toBe("compatible");
  });

  it("returns empty for repo with no lock files", async () => {
    const { scanDependencies } = await import("../scanner/dependencies");
    const { risks, licenses } = scanDependencies(tmpDir);

    expect(risks.length).toBe(0);
    expect(licenses.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Artifacts tests
// ---------------------------------------------------------------------------
describe("artifacts", () => {
  it("generateScanJSON returns valid JSON", async () => {
    const { generateScanJSON } = await import("../scanner/artifacts");
    const mockResult = {
      id: "test-123",
      profile: "quick" as const,
      inventory: {
        languages: [{ name: "TypeScript", percentage: 80, files: 10 }],
        buildSystems: ["npm"],
        ciPlatforms: ["github-actions"],
        projectType: "application",
        frameworks: ["Next.js"],
        totalFiles: 50,
        totalLines: 2000,
        repoSize: "1.2M",
      },
      safetyBoundaries: null,
      securitySignals: null,
      commitSha: "abc123",
      scannerVersion: "1.0.0",
      scannedAt: "2024-01-01T00:00:00Z",
      duration: 500,
      artifactPath: null,
    };

    const json = generateScanJSON(mockResult);
    const parsed = JSON.parse(json);
    expect(parsed.id).toBe("test-123");
    expect(parsed.inventory.languages).toHaveLength(1);
  });

  it("generateScanSummary returns markdown", async () => {
    const { generateScanSummary } = await import("../scanner/artifacts");
    const mockResult = {
      id: "test-123",
      profile: "quick" as const,
      inventory: {
        languages: [{ name: "TypeScript", percentage: 80, files: 10 }],
        buildSystems: ["npm"],
        ciPlatforms: [],
        projectType: "application",
        frameworks: [],
        totalFiles: 50,
        totalLines: 2000,
        repoSize: "1.2M",
      },
      safetyBoundaries: null,
      securitySignals: null,
      commitSha: "abc123",
      scannerVersion: "1.0.0",
      scannedAt: "2024-01-01T00:00:00Z",
      duration: 500,
      artifactPath: null,
    };

    const md = generateScanSummary(mockResult);
    expect(md).toContain("# Repository Scan Report");
    expect(md).toContain("TypeScript");
    expect(md).toContain("npm");
  });
});

// ---------------------------------------------------------------------------
// Profile orchestrator tests
// ---------------------------------------------------------------------------
describe("runLocalScan", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "atlasbridge-test-"));
    const { execFileSync } = require("child_process");
    execFileSync("git", ["init"], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["config", "user.email", "test@test.com"], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["config", "user.name", "Test"], { cwd: tmpDir, stdio: "pipe" });

    // Create a minimal repo
    const fullPath = path.join(tmpDir, "src/index.ts");
    fs.mkdirSync(path.dirname(fullPath), { recursive: true });
    fs.writeFileSync(fullPath, 'console.log("hello");');
    fs.writeFileSync(path.join(tmpDir, "package.json"), '{"name": "test"}');
    execFileSync("git", ["add", "."], { cwd: tmpDir, stdio: "pipe" });
    execFileSync("git", ["commit", "-m", "init"], { cwd: tmpDir, stdio: "pipe" });
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it("quick profile returns inventory only", async () => {
    const { runLocalScan } = await import("../scanner/profiles");
    const result = await runLocalScan(tmpDir, "quick", 1);

    expect(result.profile).toBe("quick");
    expect(result.inventory).toBeDefined();
    expect(result.inventory.totalFiles).toBeGreaterThan(0);
    expect(result.safetyBoundaries).toBeNull();
    expect(result.securitySignals).toBeNull();
    expect(result.commitSha).not.toBe("unknown");
    expect(result.scannerVersion).toBe("1.0.0");
    expect(result.duration).toBeGreaterThanOrEqual(0);
  });

  it("safety profile includes boundaries", async () => {
    const { runLocalScan } = await import("../scanner/profiles");
    const result = await runLocalScan(tmpDir, "safety", 1);

    expect(result.profile).toBe("safety");
    expect(result.inventory).toBeDefined();
    expect(result.safetyBoundaries).toBeDefined();
    expect(result.securitySignals).toBeNull();
  });

  it("deep profile includes all layers", async () => {
    const { runLocalScan } = await import("../scanner/profiles");
    const result = await runLocalScan(tmpDir, "deep", 1);

    expect(result.profile).toBe("deep");
    expect(result.inventory).toBeDefined();
    expect(result.safetyBoundaries).toBeDefined();
    expect(result.securitySignals).toBeDefined();
    expect(result.securitySignals!.totalSecretsFound).toBeDefined();
  });

  it("generates artifacts on disk", async () => {
    const { runLocalScan } = await import("../scanner/profiles");
    const result = await runLocalScan(tmpDir, "quick", 999);

    expect(result.artifactPath).toBeDefined();
    expect(fs.existsSync(path.join(result.artifactPath!, "repo_scan.json"))).toBe(true);
    expect(fs.existsSync(path.join(result.artifactPath!, "repo_scan_summary.md"))).toBe(true);
    expect(fs.existsSync(path.join(result.artifactPath!, "manifest.json"))).toBe(true);

    // Cleanup artifacts
    fs.rmSync(result.artifactPath!, { recursive: true, force: true });
  });
});
