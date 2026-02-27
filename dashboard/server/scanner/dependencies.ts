/**
 * Dependency scanner — parses lock files to extract package names, versions,
 * and license information. No CVE database lookups — structural analysis only.
 */

import fs from "fs";
import path from "path";
import type { DependencyRisk, LicenseEntry } from "@shared/schema";
import { LICENSE_PATTERNS } from "./patterns";

export interface ParsedDependency {
  name: string;
  version: string;
  license?: string;
  ecosystem: "npm" | "PyPI" | "crates.io" | "Go";
}

// ---------------------------------------------------------------------------
// Lock file parsers
// ---------------------------------------------------------------------------

function parsePackageLockJson(repoPath: string): ParsedDependency[] {
  const lockPath = path.join(repoPath, "package-lock.json");
  if (!fs.existsSync(lockPath)) return [];

  try {
    const data = JSON.parse(fs.readFileSync(lockPath, "utf-8"));
    const deps: ParsedDependency[] = [];

    // package-lock.json v2/v3 format
    if (data.packages) {
      for (const [pkgPath, info] of Object.entries(data.packages) as [string, any][]) {
        if (!pkgPath || pkgPath === "") continue; // root package
        const name = pkgPath.replace(/^node_modules\//, "");
        if (name.includes("node_modules/")) continue; // skip nested
        deps.push({
          name,
          version: info.version || "unknown",
          license: info.license || undefined,
          ecosystem: "npm",
        });
      }
    }
    // v1 format fallback
    else if (data.dependencies) {
      for (const [name, info] of Object.entries(data.dependencies) as [string, any][]) {
        deps.push({
          name,
          version: info.version || "unknown",
          ecosystem: "npm",
        });
      }
    }

    return deps;
  } catch {
    return [];
  }
}

function parseYarnLock(repoPath: string): ParsedDependency[] {
  const lockPath = path.join(repoPath, "yarn.lock");
  if (!fs.existsSync(lockPath)) return [];

  try {
    const content = fs.readFileSync(lockPath, "utf-8");
    const deps: ParsedDependency[] = [];
    const seen = new Set<string>();

    // Simple parser: look for "name@version:" followed by "version:" line
    const lines = content.split("\n");
    let currentName = "";
    for (const line of lines) {
      // Match package header like: "@babel/core@^7.0.0":
      const headerMatch = line.match(/^"?(@?[^@\s"]+)@/);
      if (headerMatch && !line.startsWith(" ")) {
        currentName = headerMatch[1];
      }
      // Match version line
      const versionMatch = line.match(/^\s+version\s+"?([^"\s]+)"?/);
      if (versionMatch && currentName) {
        const key = `${currentName}@${versionMatch[1]}`;
        if (!seen.has(key)) {
          seen.add(key);
          deps.push({ name: currentName, version: versionMatch[1], ecosystem: "npm" });
        }
      }
    }

    return deps;
  } catch {
    return [];
  }
}

function parsePoetryLock(repoPath: string): ParsedDependency[] {
  const lockPath = path.join(repoPath, "poetry.lock");
  if (!fs.existsSync(lockPath)) return [];

  try {
    const content = fs.readFileSync(lockPath, "utf-8");
    const deps: ParsedDependency[] = [];

    // Simple TOML-like parser for poetry.lock
    const blocks = content.split(/\[\[package\]\]/);
    for (const block of blocks) {
      const nameMatch = block.match(/^name\s*=\s*"([^"]+)"/m);
      const versionMatch = block.match(/^version\s*=\s*"([^"]+)"/m);
      if (nameMatch && versionMatch) {
        deps.push({ name: nameMatch[1], version: versionMatch[1], ecosystem: "PyPI" });
      }
    }

    return deps;
  } catch {
    return [];
  }
}

function parseCargoLock(repoPath: string): ParsedDependency[] {
  const lockPath = path.join(repoPath, "Cargo.lock");
  if (!fs.existsSync(lockPath)) return [];

  try {
    const content = fs.readFileSync(lockPath, "utf-8");
    const deps: ParsedDependency[] = [];

    const blocks = content.split(/\[\[package\]\]/);
    for (const block of blocks) {
      const nameMatch = block.match(/^name\s*=\s*"([^"]+)"/m);
      const versionMatch = block.match(/^version\s*=\s*"([^"]+)"/m);
      if (nameMatch && versionMatch) {
        deps.push({ name: nameMatch[1], version: versionMatch[1], ecosystem: "crates.io" });
      }
    }

    return deps;
  } catch {
    return [];
  }
}

function parseGoSum(repoPath: string): ParsedDependency[] {
  const sumPath = path.join(repoPath, "go.sum");
  if (!fs.existsSync(sumPath)) return [];

  try {
    const content = fs.readFileSync(sumPath, "utf-8");
    const deps: ParsedDependency[] = [];
    const seen = new Set<string>();

    for (const line of content.split("\n")) {
      const parts = line.trim().split(/\s+/);
      if (parts.length >= 2) {
        const name = parts[0];
        const version = parts[1].replace(/\/go\.mod$/, "");
        const key = `${name}@${version}`;
        if (!seen.has(key)) {
          seen.add(key);
          deps.push({ name, version, ecosystem: "Go" });
        }
      }
    }

    return deps;
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// License detection
// ---------------------------------------------------------------------------

function detectProjectLicense(repoPath: string): string | null {
  for (const name of ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "LICENCE.md"]) {
    const licensePath = path.join(repoPath, name);
    if (fs.existsSync(licensePath)) {
      try {
        const content = fs.readFileSync(licensePath, "utf-8");
        for (const { pattern, spdx } of LICENSE_PATTERNS) {
          if (pattern.test(content)) return spdx;
        }
        return "Unknown";
      } catch {
        return "Unknown";
      }
    }
  }
  return null;
}

function classifyLicenseRisk(license: string): "compatible" | "review" | "incompatible" {
  const entry = LICENSE_PATTERNS.find((p) => p.spdx === license);
  return entry?.risk ?? "review";
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function parseDependencies(repoPath: string): ParsedDependency[] {
  return [
    ...parsePackageLockJson(repoPath),
    ...parseYarnLock(repoPath),
    ...parsePoetryLock(repoPath),
    ...parseCargoLock(repoPath),
    ...parseGoSum(repoPath),
  ];
}

export function scanDependencies(repoPath: string): {
  risks: DependencyRisk[];
  licenses: LicenseEntry[];
} {
  const allDeps = parseDependencies(repoPath);

  // Build dependency risks
  const risks: DependencyRisk[] = [];
  const licenseEntries: LicenseEntry[] = [];
  const projectLicense = detectProjectLicense(repoPath);

  // Check for packages with no license (from package-lock where license is known)
  for (const dep of allDeps) {
    // Flag packages with no license
    if (dep.license === undefined || dep.license === "") {
      risks.push({
        name: dep.name,
        version: dep.version,
        risk: "unknown-license",
        detail: "No license information available for this package",
      });
    } else if (dep.license) {
      const risk = classifyLicenseRisk(dep.license);
      if (risk === "incompatible") {
        risks.push({
          name: dep.name,
          version: dep.version,
          risk: "license-incompatible",
          detail: `License ${dep.license} may be incompatible with your project`,
        });
      }
      licenseEntries.push({
        name: dep.name,
        license: dep.license,
        risk,
      });
    }
  }

  // Add project license if detected
  if (projectLicense) {
    licenseEntries.unshift({
      name: "(project)",
      license: projectLicense,
      risk: classifyLicenseRisk(projectLicense),
    });
  }

  // Limit results to keep response manageable
  return {
    risks: risks.slice(0, 50),
    licenses: licenseEntries.slice(0, 100),
  };
}
