/**
 * CVE vulnerability lookups — OSV.dev (primary) with GitHub Advisory fallback.
 * All API failures return empty arrays; scans are never blocked by CVE API downtime.
 */

import type { VulnerabilityFinding } from "@shared/schema";
import type { ParsedDependency } from "./dependencies";

// ---------------------------------------------------------------------------
// OSV.dev batch API
// ---------------------------------------------------------------------------

interface OsvQuery {
  package: { name: string; ecosystem: string };
  version: string;
}

interface OsvVulnerability {
  id: string;
  summary?: string;
  details?: string;
  severity?: { type: string; score: string }[];
  affected?: {
    package?: { name: string; ecosystem: string };
    ranges?: { type: string; events: { introduced?: string; fixed?: string }[] }[];
  }[];
  references?: { type: string; url: string }[];
}

interface OsvBatchResponse {
  results: { vulns?: OsvVulnerability[] }[];
}

function mapSeverity(cvss: number | null): VulnerabilityFinding["severity"] {
  if (cvss === null) return "unknown";
  if (cvss >= 9.0) return "critical";
  if (cvss >= 7.0) return "high";
  if (cvss >= 4.0) return "medium";
  return "low";
}

function extractCvssScore(vuln: OsvVulnerability): number | null {
  if (!vuln.severity) return null;
  for (const s of vuln.severity) {
    if (s.type === "CVSS_V3" || s.type === "CVSS_V2") {
      const score = parseFloat(s.score);
      if (!isNaN(score)) return score;
    }
  }
  return null;
}

function extractFixVersion(vuln: OsvVulnerability): string | null {
  if (!vuln.affected) return null;
  for (const a of vuln.affected) {
    if (!a.ranges) continue;
    for (const r of a.ranges) {
      for (const e of r.events) {
        if (e.fixed) return e.fixed;
      }
    }
  }
  return null;
}

function extractAdvisoryUrl(vuln: OsvVulnerability): string | null {
  if (!vuln.references) return null;
  const advisory = vuln.references.find(
    (r) => r.type === "ADVISORY" || r.type === "WEB",
  );
  return advisory?.url ?? null;
}

async function queryOsvBatch(
  queries: OsvQuery[],
): Promise<OsvBatchResponse | null> {
  try {
    const res = await fetch("https://api.osv.dev/v1/querybatch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ queries }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) return null;
    return (await res.json()) as OsvBatchResponse;
  } catch {
    return null;
  }
}

async function lookupOsv(
  deps: ParsedDependency[],
): Promise<VulnerabilityFinding[]> {
  if (deps.length === 0) return [];

  const findings: VulnerabilityFinding[] = [];
  const seen = new Set<string>();

  // Batch in groups of 100 (OSV limit)
  const BATCH_SIZE = 100;
  const startTime = Date.now();

  for (let i = 0; i < deps.length; i += BATCH_SIZE) {
    // Total timeout: 30s
    if (Date.now() - startTime > 30_000) break;

    const batch = deps.slice(i, i + BATCH_SIZE);
    const queries: OsvQuery[] = batch.map((d) => ({
      package: { name: d.name, ecosystem: d.ecosystem },
      version: d.version,
    }));

    const response = await queryOsvBatch(queries);
    if (!response) continue;

    for (let j = 0; j < response.results.length; j++) {
      const vulns = response.results[j].vulns;
      if (!vulns || vulns.length === 0) continue;
      const dep = batch[j];

      for (const vuln of vulns) {
        const key = `${vuln.id}:${dep.name}:${dep.version}`;
        if (seen.has(key)) continue;
        seen.add(key);

        const cvssScore = extractCvssScore(vuln);

        findings.push({
          cveId: vuln.id,
          packageName: dep.name,
          packageVersion: dep.version,
          ecosystem: dep.ecosystem,
          severity: mapSeverity(cvssScore),
          cvssScore,
          summary: vuln.summary || vuln.details?.slice(0, 200) || "No description available",
          advisoryUrl: extractAdvisoryUrl(vuln),
          fixVersion: extractFixVersion(vuln),
          source: "osv",
        });
      }
    }
  }

  return findings;
}

// ---------------------------------------------------------------------------
// GitHub Security Advisories (GraphQL fallback)
// ---------------------------------------------------------------------------

const GITHUB_ADVISORY_QUERY = `
query($ecosystem: SecurityAdvisoryEcosystem!, $package: String!) {
  securityVulnerabilities(first: 10, ecosystem: $ecosystem, package: $package) {
    nodes {
      advisory { ghsaId summary severity cvss { score } references { url } }
      vulnerableVersionRange
      firstPatchedVersion { identifier }
      package { name ecosystem }
    }
  }
}`;

function mapGitHubEcosystem(ecosystem: string): string | null {
  const map: Record<string, string> = {
    npm: "NPM",
    PyPI: "PIP",
    "crates.io": "RUST",
    Go: "GO",
  };
  return map[ecosystem] ?? null;
}

function mapGitHubSeverity(severity: string): VulnerabilityFinding["severity"] {
  switch (severity?.toUpperCase()) {
    case "CRITICAL": return "critical";
    case "HIGH": return "high";
    case "MODERATE": return "medium";
    case "LOW": return "low";
    default: return "unknown";
  }
}

async function lookupGitHubAdvisories(
  deps: ParsedDependency[],
  token: string,
): Promise<VulnerabilityFinding[]> {
  const findings: VulnerabilityFinding[] = [];
  const seen = new Set<string>();

  // Only query first 50 packages to stay within rate limits
  for (const dep of deps.slice(0, 50)) {
    const ghEco = mapGitHubEcosystem(dep.ecosystem);
    if (!ghEco) continue;

    try {
      const res = await fetch("https://api.github.com/graphql", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: GITHUB_ADVISORY_QUERY,
          variables: { ecosystem: ghEco, package: dep.name },
        }),
        signal: AbortSignal.timeout(5_000),
      });

      if (!res.ok) continue;

      const data = (await res.json()) as {
        data?: {
          securityVulnerabilities?: {
            nodes?: {
              advisory?: {
                ghsaId?: string;
                summary?: string;
                severity?: string;
                cvss?: { score?: number };
                references?: { url: string }[];
              };
              firstPatchedVersion?: { identifier?: string };
            }[];
          };
        };
      };

      const nodes = data.data?.securityVulnerabilities?.nodes ?? [];
      for (const node of nodes) {
        const advisory = node.advisory;
        if (!advisory?.ghsaId) continue;

        const key = `${advisory.ghsaId}:${dep.name}:${dep.version}`;
        if (seen.has(key)) continue;
        seen.add(key);

        findings.push({
          cveId: advisory.ghsaId,
          packageName: dep.name,
          packageVersion: dep.version,
          ecosystem: dep.ecosystem,
          severity: mapGitHubSeverity(advisory.severity || ""),
          cvssScore: advisory.cvss?.score ?? null,
          summary: advisory.summary || "No description",
          advisoryUrl: advisory.references?.[0]?.url ?? null,
          fixVersion: node.firstPatchedVersion?.identifier ?? null,
          source: "github-advisory",
        });
      }
    } catch {
      // Continue to next package on error
    }
  }

  return findings;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function scanVulnerabilities(
  deps: ParsedDependency[],
  options?: { githubToken?: string },
): Promise<VulnerabilityFinding[]> {
  try {
    // Primary: OSV.dev
    const osvFindings = await lookupOsv(deps);

    // Fallback: GitHub Advisories for packages OSV didn't cover
    if (options?.githubToken) {
      const osvCovered = new Set(
        osvFindings.map((f) => `${f.packageName}:${f.packageVersion}`),
      );
      const uncovered = deps.filter(
        (d) => !osvCovered.has(`${d.name}:${d.version}`),
      );

      if (uncovered.length > 0) {
        const ghFindings = await lookupGitHubAdvisories(
          uncovered,
          options.githubToken,
        );
        return [...osvFindings, ...ghFindings].slice(0, 200);
      }
    }

    return osvFindings.slice(0, 200);
  } catch {
    return [];
  }
}
