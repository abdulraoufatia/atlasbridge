/**
 * Local filesystem scanner — walks a repo directory to build inventory,
 * detect safety boundaries, and identify security signals.
 */

import fs from "fs";
import path from "path";
import { execFileSync } from "child_process";
import { createHash } from "crypto";
import type {
  RepoInventory,
  SafetyBoundary,
  LanguageBreakdown,
  SensitivePathEntry,
  ToolSurface,
  CISafetyCheck,
} from "@shared/schema";
import {
  LANGUAGE_EXTENSIONS,
  BUILD_SYSTEM_FILES,
  CI_CONFIG_FILES,
  FRAMEWORK_INDICATORS,
  SENSITIVE_PATH_PATTERNS,
  TOOL_SURFACE_DIRS,
  SKIP_DIRS,
} from "./patterns";

// ---------------------------------------------------------------------------
// Git helpers
// ---------------------------------------------------------------------------

export function getCommitSha(repoPath: string): string {
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], { cwd: repoPath, timeout: 5000, encoding: "utf-8" }).trim();
  } catch {
    return "unknown";
  }
}

export function cloneRepo(url: string, branch: string, destDir: string, accessToken?: string | null): void {
  let cloneUrl = url;
  if (accessToken && url.startsWith("https://")) {
    // Inject token into URL for private repo access
    const parsed = new URL(url);
    parsed.username = "x-access-token";
    parsed.password = accessToken;
    cloneUrl = parsed.toString();
  }
  execFileSync("git", ["clone", "--depth", "1", "--branch", branch, cloneUrl, destDir], {
    timeout: 60_000,
    encoding: "utf-8",
    stdio: "pipe",
  });
}

// ---------------------------------------------------------------------------
// File listing
// ---------------------------------------------------------------------------

function listFiles(repoPath: string): string[] {
  // Prefer git ls-files for accuracy (respects .gitignore)
  try {
    const output = execFileSync("git", ["ls-files"], {
      cwd: repoPath,
      timeout: 15_000,
      encoding: "utf-8",
      maxBuffer: 10 * 1024 * 1024,
    });
    return output.split("\n").filter((l) => l.trim());
  } catch {
    // Fallback: walk directory manually
    return walkDir(repoPath, repoPath);
  }
}

function walkDir(base: string, current: string): string[] {
  const results: string[] = [];
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(current, { withFileTypes: true });
  } catch {
    return results;
  }
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry.name)) continue;
    const fullPath = path.join(current, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkDir(base, fullPath));
    } else if (entry.isFile()) {
      results.push(path.relative(base, fullPath));
    }
  }
  return results;
}

// ---------------------------------------------------------------------------
// Layer 1: Inventory
// ---------------------------------------------------------------------------

export function scanInventory(repoPath: string): RepoInventory {
  const files = listFiles(repoPath);
  const totalFiles = files.length;

  // Language detection
  const langCounts: Record<string, number> = {};
  let totalCountedFiles = 0;
  for (const file of files) {
    const ext = path.extname(file).toLowerCase();
    const lang = LANGUAGE_EXTENSIONS[ext];
    if (lang) {
      langCounts[lang] = (langCounts[lang] || 0) + 1;
      totalCountedFiles++;
    }
  }

  const languages: LanguageBreakdown[] = Object.entries(langCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({
      name,
      percentage: totalCountedFiles > 0 ? Math.round((count / totalCountedFiles) * 1000) / 10 : 0,
      files: count,
    }));

  // Build system detection
  const buildSystems: string[] = [];
  const fileSet = new Set(files);
  for (const [configFile, system] of Object.entries(BUILD_SYSTEM_FILES)) {
    if (fileSet.has(configFile) && !buildSystems.includes(system)) {
      buildSystems.push(system);
    }
  }

  // CI platform detection
  const ciPlatforms: string[] = [];
  for (const [configPath, platform] of Object.entries(CI_CONFIG_FILES)) {
    const found = configPath.endsWith("/")
      ? files.some((f) => f.startsWith(configPath))
      : configPath.includes("/")
        ? files.some((f) => f === configPath || f.startsWith(configPath + "/"))
        : fileSet.has(configPath);
    // For .github/workflows, check if any yaml files exist under it
    if (!found && configPath === ".github/workflows") {
      if (files.some((f) => f.startsWith(".github/workflows/") && (f.endsWith(".yml") || f.endsWith(".yaml")))) {
        ciPlatforms.push(platform);
        continue;
      }
    }
    if (found && !ciPlatforms.includes(platform)) {
      ciPlatforms.push(platform);
    }
  }

  // Framework detection
  const frameworks: string[] = [];
  for (const [indicator, framework] of Object.entries(FRAMEWORK_INDICATORS)) {
    if (fileSet.has(indicator) && !frameworks.includes(framework)) {
      frameworks.push(framework);
    }
  }

  // Project type inference
  const projectType = inferProjectType(files, fileSet, buildSystems);

  // Total lines (approximate — count only code files, cap at 1000 files for performance)
  let totalLines = 0;
  const codeFiles = files.filter((f) => {
    const ext = path.extname(f).toLowerCase();
    return LANGUAGE_EXTENSIONS[ext] !== undefined;
  });
  const filesToCount = codeFiles.slice(0, 1000);
  for (const file of filesToCount) {
    try {
      const content = fs.readFileSync(path.join(repoPath, file), "utf-8");
      totalLines += content.split("\n").length;
    } catch {
      // skip unreadable files
    }
  }
  if (codeFiles.length > 1000) {
    // Extrapolate
    totalLines = Math.round(totalLines * (codeFiles.length / 1000));
  }

  // Repo size
  let repoSize = "unknown";
  try {
    const sizeOutput = execFileSync("du", ["-sh", repoPath], { timeout: 5000, encoding: "utf-8" });
    repoSize = sizeOutput.split("\t")[0].trim();
  } catch {
    // skip
  }

  return {
    languages,
    buildSystems,
    ciPlatforms,
    projectType,
    frameworks,
    totalFiles,
    totalLines,
    repoSize,
  };
}

function inferProjectType(files: string[], fileSet: Set<string>, buildSystems: string[]): string {
  // Check for monorepo indicators
  const packageJsonCount = files.filter((f) => f.endsWith("package.json") && f.includes("/")).length;
  if (packageJsonCount >= 3 || fileSet.has("lerna.json") || fileSet.has("pnpm-workspace.yaml") || fileSet.has("nx.json")) {
    return "monorepo";
  }

  // Check for library indicators
  if (fileSet.has("setup.py") || fileSet.has("setup.cfg") || fileSet.has("pyproject.toml")) {
    // If it has entry points / CLI, it's an application
    if (files.some((f) => f.includes("cli/") || f.includes("__main__.py"))) {
      return "application";
    }
    return "library";
  }

  // npm package with main/exports → library
  if (fileSet.has("package.json")) {
    try {
      const pkg = JSON.parse(fs.readFileSync(path.join(files[0] ? path.dirname(files[0]) : "", "package.json"), "utf-8"));
      if (pkg.main || pkg.exports) return "library";
    } catch {
      // ignore
    }
  }

  if (fileSet.has("Cargo.toml")) {
    // Check if it's a binary or library
    if (files.some((f) => f === "src/main.rs")) return "application";
    if (files.some((f) => f === "src/lib.rs")) return "library";
  }

  // Check for web app indicators
  if (files.some((f) => f.startsWith("public/") || f.startsWith("static/"))) {
    return "web-application";
  }

  // Default: if it has build systems, it's an application
  if (buildSystems.length > 0) return "application";

  return "unknown";
}

// ---------------------------------------------------------------------------
// Layer 2: Safety Boundaries
// ---------------------------------------------------------------------------

export function scanSafetyBoundaries(repoPath: string): SafetyBoundary {
  const files = listFiles(repoPath);

  // Sensitive path detection
  const sensitivePaths: SensitivePathEntry[] = [];
  for (const file of files) {
    for (const pattern of SENSITIVE_PATH_PATTERNS) {
      if (pattern.pattern.test(file)) {
        sensitivePaths.push({
          path: file,
          reason: pattern.reason,
          risk: pattern.risk,
        });
        break; // one match per file is enough
      }
    }
  }

  // Tool surface detection
  const toolSurfaces: ToolSurface[] = [];
  const fileSet = new Set(files);
  for (const [dir, tool] of Object.entries(TOOL_SURFACE_DIRS)) {
    const hasDir = files.some((f) => f === dir || f.startsWith(dir + "/"));
    if (hasDir) {
      // Determine risk based on tool type
      const isAITool = ["Claude Code", "Cursor", "GitHub Copilot", "Aider", "Continue", "Codeium", "Tabnine"].includes(tool);
      toolSurfaces.push({
        tool,
        configPath: dir,
        risk: isAITool ? "Review AI tool permissions and allowed actions" : "Standard development tool",
      });
    }
  }

  // CI safety checks
  const ciSafetyChecks = detectCISafetyChecks(repoPath, files);

  return {
    sensitivePaths,
    toolSurfaces,
    policyCoverage: null, // Deferred — requires Python CLI bridge
    ciSafetyChecks,
  };
}

function detectCISafetyChecks(repoPath: string, files: string[]): CISafetyCheck[] {
  const checks: CISafetyCheck[] = [];

  // Find CI config files
  const ciFiles = files.filter(
    (f) =>
      f.startsWith(".github/workflows/") ||
      f === ".gitlab-ci.yml" ||
      f === "bitbucket-pipelines.yml" ||
      f === "azure-pipelines.yml",
  );

  if (ciFiles.length === 0) {
    checks.push({ name: "CI pipeline", present: false, detail: "No CI configuration found" });
    return checks;
  }

  checks.push({ name: "CI pipeline", present: true, detail: `Found ${ciFiles.length} CI config file(s)` });

  // Read CI files and check for common safety steps
  let ciContent = "";
  for (const ciFile of ciFiles.slice(0, 5)) {
    try {
      ciContent += fs.readFileSync(path.join(repoPath, ciFile), "utf-8") + "\n";
    } catch {
      // skip
    }
  }

  const ciContentLower = ciContent.toLowerCase();

  checks.push({
    name: "Linting step",
    present: /lint|eslint|ruff|flake8|pylint|clippy|golangci/.test(ciContentLower),
    detail: /lint|eslint|ruff/.test(ciContentLower) ? "Linting step detected in CI" : "No linting step found in CI",
  });

  checks.push({
    name: "Type checking",
    present: /tsc|mypy|pyright|typecheck|type-check/.test(ciContentLower),
    detail: /tsc|mypy|pyright/.test(ciContentLower) ? "Type checking step detected" : "No type checking step found",
  });

  checks.push({
    name: "Test execution",
    present: /test|pytest|jest|vitest|cargo test|go test/.test(ciContentLower),
    detail: /test|pytest|jest|vitest/.test(ciContentLower) ? "Test step detected in CI" : "No test step found in CI",
  });

  checks.push({
    name: "Security scanning",
    present: /security|bandit|semgrep|snyk|trivy|codeql|gitleaks|trufflehog/.test(ciContentLower),
    detail: /bandit|semgrep|snyk|trivy|codeql/.test(ciContentLower) ? "Security scanning step detected" : "No security scanning step found",
  });

  checks.push({
    name: "Branch protection",
    present: /pull_request|merge_request|on:\s*\[.*pull/.test(ciContent),
    detail: /pull_request|merge_request/.test(ciContent) ? "CI runs on pull requests" : "CI may not be gating pull requests",
  });

  return checks;
}
