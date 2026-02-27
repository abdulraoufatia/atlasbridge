/**
 * Artifact generation — produces scan report files (JSON + markdown summary).
 */

import fs from "fs";
import path from "path";
import { createHash } from "crypto";
import type { LocalScanResult } from "@shared/schema";
import { getArtifactsDir, ensureDir } from "../config";

function sha256(data: string): string {
  return createHash("sha256").update(data).digest("hex");
}

export function generateScanJSON(result: LocalScanResult): string {
  return JSON.stringify(result, null, 2);
}

export function generateScanSummary(result: LocalScanResult): string {
  const lines: string[] = [];
  lines.push(`# Repository Scan Report`);
  lines.push("");
  lines.push(`- **Profile:** ${result.profile}`);
  lines.push(`- **Commit:** ${result.commitSha}`);
  lines.push(`- **Scanner Version:** ${result.scannerVersion}`);
  lines.push(`- **Scanned At:** ${result.scannedAt}`);
  lines.push(`- **Duration:** ${result.duration}ms`);
  lines.push("");

  // Inventory
  const inv = result.inventory;
  lines.push("## Inventory");
  lines.push("");
  lines.push(`- **Total Files:** ${inv.totalFiles}`);
  lines.push(`- **Total Lines:** ${inv.totalLines.toLocaleString()}`);
  lines.push(`- **Repo Size:** ${inv.repoSize}`);
  lines.push(`- **Project Type:** ${inv.projectType}`);
  lines.push("");

  if (inv.languages.length > 0) {
    lines.push("### Languages");
    lines.push("");
    for (const lang of inv.languages.slice(0, 10)) {
      lines.push(`- ${lang.name}: ${lang.percentage}% (${lang.files} files)`);
    }
    lines.push("");
  }

  if (inv.buildSystems.length > 0) {
    lines.push(`**Build Systems:** ${inv.buildSystems.join(", ")}`);
    lines.push("");
  }

  if (inv.ciPlatforms.length > 0) {
    lines.push(`**CI Platforms:** ${inv.ciPlatforms.join(", ")}`);
    lines.push("");
  }

  if (inv.frameworks.length > 0) {
    lines.push(`**Frameworks:** ${inv.frameworks.join(", ")}`);
    lines.push("");
  }

  // Safety Boundaries
  if (result.safetyBoundaries) {
    const sb = result.safetyBoundaries;
    lines.push("## Safety Boundaries");
    lines.push("");

    if (sb.sensitivePaths.length > 0) {
      lines.push(`### Sensitive Paths (${sb.sensitivePaths.length})`);
      lines.push("");
      for (const sp of sb.sensitivePaths.slice(0, 20)) {
        lines.push(`- [${sp.risk.toUpperCase()}] \`${sp.path}\` - ${sp.reason}`);
      }
      lines.push("");
    }

    if (sb.toolSurfaces.length > 0) {
      lines.push("### Tool Surfaces");
      lines.push("");
      for (const ts of sb.toolSurfaces) {
        lines.push(`- **${ts.tool}** (\`${ts.configPath}\`) - ${ts.risk}`);
      }
      lines.push("");
    }

    if (sb.ciSafetyChecks.length > 0) {
      lines.push("### CI Safety Checks");
      lines.push("");
      for (const check of sb.ciSafetyChecks) {
        const icon = check.present ? "PASS" : "FAIL";
        lines.push(`- [${icon}] ${check.name}: ${check.detail}`);
      }
      lines.push("");
    }
  }

  // Security Signals
  if (result.securitySignals) {
    const ss = result.securitySignals;
    lines.push("## Security Signals");
    lines.push("");

    lines.push(`### Secrets (${ss.totalSecretsFound} findings)`);
    lines.push("");
    if (ss.secretFindings.length > 0) {
      for (const sf of ss.secretFindings.slice(0, 20)) {
        lines.push(`- \`${sf.file}:${sf.line}\` - ${sf.type} (fingerprint: ${sf.fingerprint})`);
      }
    } else {
      lines.push("No secrets detected.");
    }
    lines.push("");

    if (ss.dependencyRisks.length > 0) {
      lines.push(`### Dependency Risks (${ss.dependencyRisks.length})`);
      lines.push("");
      for (const dr of ss.dependencyRisks.slice(0, 20)) {
        lines.push(`- **${dr.name}@${dr.version}** - ${dr.risk}: ${dr.detail}`);
      }
      lines.push("");
    }

    if (ss.licenseInventory.length > 0) {
      lines.push(`### License Inventory (${ss.licenseInventory.length})`);
      lines.push("");
      for (const le of ss.licenseInventory.slice(0, 20)) {
        lines.push(`- ${le.name}: ${le.license} (${le.risk})`);
      }
      lines.push("");
    }

    if (ss.vulnerabilities && ss.vulnerabilities.length > 0) {
      lines.push(`### Vulnerabilities (${ss.totalVulnerabilities} found, ${ss.criticalVulnerabilities} critical)`);
      lines.push("");
      for (const v of ss.vulnerabilities.slice(0, 30)) {
        lines.push(`- [${v.severity.toUpperCase()}] **${v.cveId}** — ${v.packageName}@${v.packageVersion}: ${v.summary}`);
        if (v.fixVersion) lines.push(`  Fix: upgrade to ${v.fixVersion}`);
      }
      lines.push("");
    }
  }

  return lines.join("\n");
}

export function saveArtifacts(
  repoConnectionId: number,
  scanId: string,
  result: LocalScanResult,
): string {
  const artifactsDir = path.join(getArtifactsDir(), String(repoConnectionId), scanId);
  ensureDir(artifactsDir);

  const jsonContent = generateScanJSON(result);
  const summaryContent = generateScanSummary(result);

  fs.writeFileSync(path.join(artifactsDir, "repo_scan.json"), jsonContent, "utf-8");
  fs.writeFileSync(path.join(artifactsDir, "repo_scan_summary.md"), summaryContent, "utf-8");

  // Write manifest with hashes
  const manifest = {
    scanId,
    commitSha: result.commitSha,
    scannerVersion: result.scannerVersion,
    scannedAt: result.scannedAt,
    files: {
      "repo_scan.json": sha256(jsonContent),
      "repo_scan_summary.md": sha256(summaryContent),
    },
  };
  fs.writeFileSync(path.join(artifactsDir, "manifest.json"), JSON.stringify(manifest, null, 2), "utf-8");

  return artifactsDir;
}
