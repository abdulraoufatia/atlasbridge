/**
 * Container image scanning — shells out to Trivy for vulnerability detection.
 * Gracefully handles Trivy not being installed.
 */

import { execFile } from "child_process";
import { promisify } from "util";
import type { ContainerScanResult, ContainerVulnerability } from "@shared/schema";

const execFileAsync = promisify(execFile);

async function isTrivyAvailable(): Promise<boolean> {
  try {
    await execFileAsync("which", ["trivy"]);
    return true;
  } catch {
    return false;
  }
}

interface TrivyResult {
  SchemaVersion?: number;
  Results?: {
    Target: string;
    Type: string;
    Vulnerabilities?: {
      VulnerabilityID: string;
      PkgName: string;
      InstalledVersion: string;
      FixedVersion?: string;
      Severity: string;
      Title?: string;
    }[];
  }[];
  Metadata?: {
    OS?: { Family?: string; Name?: string };
  };
}

function mapTrivySeverity(severity: string): ContainerVulnerability["severity"] {
  switch (severity?.toUpperCase()) {
    case "CRITICAL": return "critical";
    case "HIGH": return "high";
    case "MEDIUM": return "medium";
    case "LOW": return "low";
    default: return "unknown";
  }
}

export async function scanContainerImage(
  image: string,
  tag: string,
): Promise<ContainerScanResult> {
  const available = await isTrivyAvailable();
  if (!available) {
    return {
      available: false,
      image,
      tag,
      os: null,
      vulnerabilities: [],
      totalVulnerabilities: 0,
      criticalCount: 0,
      highCount: 0,
      scannedAt: new Date().toISOString(),
      error: "Trivy not found. Install it with: brew install trivy (macOS) or see https://trivy.dev",
    };
  }

  try {
    const imageRef = `${image}:${tag}`;
    const { stdout } = await execFileAsync(
      "trivy",
      ["image", "--format", "json", "--quiet", imageRef],
      { timeout: 120_000, maxBuffer: 10 * 1024 * 1024 },
    );

    const data = JSON.parse(stdout) as TrivyResult;

    const vulnerabilities: ContainerVulnerability[] = [];
    for (const result of data.Results ?? []) {
      for (const vuln of result.Vulnerabilities ?? []) {
        vulnerabilities.push({
          id: vuln.VulnerabilityID,
          packageName: vuln.PkgName,
          installedVersion: vuln.InstalledVersion,
          fixedVersion: vuln.FixedVersion ?? null,
          severity: mapTrivySeverity(vuln.Severity),
          title: vuln.Title ?? "No description",
        });
      }
    }

    const criticalCount = vulnerabilities.filter((v) => v.severity === "critical").length;
    const highCount = vulnerabilities.filter((v) => v.severity === "high").length;

    return {
      available: true,
      image,
      tag,
      os: data.Metadata?.OS?.Family
        ? `${data.Metadata.OS.Family} ${data.Metadata.OS.Name || ""}`.trim()
        : null,
      vulnerabilities: vulnerabilities.slice(0, 200),
      totalVulnerabilities: vulnerabilities.length,
      criticalCount,
      highCount,
      scannedAt: new Date().toISOString(),
    };
  } catch (err: any) {
    return {
      available: true,
      image,
      tag,
      os: null,
      vulnerabilities: [],
      totalVulnerabilities: 0,
      criticalCount: 0,
      highCount: 0,
      scannedAt: new Date().toISOString(),
      error: err.message || "Trivy scan failed",
    };
  }
}
