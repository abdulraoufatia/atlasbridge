/**
 * Remote repository scanning — inventory analysis via provider APIs without cloning.
 * Detects languages, build systems, CI, frameworks, and sensitive paths from file listings.
 */

import path from "path";
import type { RepoInventory, SensitivePathEntry, RemoteScanResult } from "@shared/schema";
import type { RepoContext, ProviderClient } from "./types";
import {
  LANGUAGE_EXTENSIONS,
  BUILD_SYSTEM_FILES,
  CI_CONFIG_FILES,
  FRAMEWORK_INDICATORS,
  SENSITIVE_PATH_PATTERNS,
} from "./patterns";

function detectLanguages(files: string[]): RepoInventory["languages"] {
  const counts: Record<string, number> = {};

  for (const file of files) {
    const ext = path.extname(file).toLowerCase();
    const lang = LANGUAGE_EXTENSIONS[ext];
    if (lang) counts[lang] = (counts[lang] || 0) + 1;
  }

  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  return Object.entries(counts)
    .map(([name, fileCount]) => ({
      name,
      percentage: Math.round((fileCount / total) * 100),
      files: fileCount,
    }))
    .sort((a, b) => b.files - a.files)
    .slice(0, 15);
}

function detectBuildSystems(files: string[]): string[] {
  const fileSet = new Set(files.map((f) => path.basename(f)));
  const systems: string[] = [];

  for (const [file, system] of Object.entries(BUILD_SYSTEM_FILES)) {
    if (fileSet.has(file)) systems.push(system);
  }

  return Array.from(new Set(systems));
}

function detectCIPlatforms(files: string[]): string[] {
  const platforms: string[] = [];

  for (const [pattern, platform] of Object.entries(CI_CONFIG_FILES)) {
    const hasMatch = files.some((f) => f.includes(pattern));
    if (hasMatch) platforms.push(platform);
  }

  return Array.from(new Set(platforms));
}

function detectFrameworks(files: string[]): string[] {
  const frameworks: string[] = [];

  for (const [indicator, framework] of Object.entries(FRAMEWORK_INDICATORS)) {
    const hasMatch = files.some((f) => f.endsWith(indicator) || path.basename(f) === indicator);
    if (hasMatch) frameworks.push(framework);
  }

  return Array.from(new Set(frameworks));
}

function detectSensitivePaths(files: string[]): SensitivePathEntry[] {
  const results: SensitivePathEntry[] = [];

  for (const file of files) {
    for (const sp of SENSITIVE_PATH_PATTERNS) {
      if (sp.pattern.test(file)) {
        results.push({ path: file, reason: sp.reason, risk: sp.risk });
        break;
      }
    }
  }

  return results.slice(0, 50);
}

export async function runRemoteScan(
  client: ProviderClient,
  ctx: RepoContext,
): Promise<RemoteScanResult> {
  const startTime = Date.now();

  if (!client.listTree) {
    throw new Error(`Provider ${ctx.provider} does not support remote scanning`);
  }

  const files = await client.listTree(ctx);

  const inventory: RepoInventory = {
    languages: detectLanguages(files),
    buildSystems: detectBuildSystems(files),
    ciPlatforms: detectCIPlatforms(files),
    projectType: "unknown",
    frameworks: detectFrameworks(files),
    totalFiles: files.length,
    totalLines: 0,
    repoSize: "N/A (remote)",
  };

  // Infer project type
  const hasMultiplePackageJson = files.filter((f) => path.basename(f) === "package.json").length > 1;
  if (hasMultiplePackageJson || files.some((f) => f.includes("lerna.json") || f.includes("pnpm-workspace.yaml"))) {
    inventory.projectType = "monorepo";
  } else if (files.some((f) => f.includes("src/") && (f.includes("index.ts") || f.includes("index.js")))) {
    inventory.projectType = "application";
  } else {
    inventory.projectType = "unknown";
  }

  const sensitivePaths = detectSensitivePaths(files);

  return {
    inventory,
    sensitivePaths,
    scannedAt: new Date().toISOString(),
    duration: Date.now() - startTime,
  };
}
