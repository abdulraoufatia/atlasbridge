/**
 * Scan profile orchestrator — coordinates scanning layers based on the
 * selected profile (quick, safety, deep).
 */

import { randomUUID } from "crypto";
import type { ScanProfile, LocalScanResult, SecuritySignal } from "@shared/schema";
import { scanInventory, scanSafetyBoundaries, getCommitSha } from "./local";
import { scanForSecrets } from "./secrets";
import { scanDependencies, parseDependencies } from "./dependencies";
import { scanVulnerabilities } from "./vulnerabilities";
import { saveArtifacts } from "./artifacts";

const SCANNER_VERSION = "1.0.0";

export async function runLocalScan(
  repoPath: string,
  profile: ScanProfile,
  repoConnectionId: number,
): Promise<LocalScanResult> {
  const startTime = Date.now();
  const scanId = randomUUID();
  const commitSha = getCommitSha(repoPath);

  // Layer 1: Inventory (always)
  const inventory = scanInventory(repoPath);

  // Layer 2: Safety Boundaries (safety + deep profiles)
  const safetyBoundaries = profile === "quick" ? null : scanSafetyBoundaries(repoPath);

  // Layer 3: Security Signals (deep profile only)
  let securitySignals: SecuritySignal | null = null;
  if (profile === "deep") {
    const secretFindings = scanForSecrets(repoPath);
    const allDeps = parseDependencies(repoPath);
    const { risks, licenses } = scanDependencies(repoPath);
    const vulnFindings = await scanVulnerabilities(allDeps);
    securitySignals = {
      secretFindings,
      dependencyRisks: risks,
      licenseInventory: licenses,
      totalSecretsFound: secretFindings.length,
      vulnerabilities: vulnFindings,
      totalVulnerabilities: vulnFindings.length,
      criticalVulnerabilities: vulnFindings.filter((v) => v.severity === "critical").length,
    };
  }

  const duration = Date.now() - startTime;

  const result: LocalScanResult = {
    id: scanId,
    profile,
    inventory,
    safetyBoundaries,
    securitySignals,
    commitSha,
    scannerVersion: SCANNER_VERSION,
    scannedAt: new Date().toISOString(),
    duration,
    artifactPath: null,
  };

  // Generate and save artifacts
  const artifactPath = saveArtifacts(repoConnectionId, scanId, result);
  result.artifactPath = artifactPath;

  return result;
}
