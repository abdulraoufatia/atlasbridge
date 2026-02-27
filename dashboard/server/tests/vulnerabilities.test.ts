import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ---------------------------------------------------------------------------
// OSV.dev + GitHub Advisory vulnerability scanning tests
// ---------------------------------------------------------------------------

describe("vulnerabilities", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns empty array for empty deps", async () => {
    const { scanVulnerabilities } = await import("../scanner/vulnerabilities");
    const result = await scanVulnerabilities([]);
    expect(result).toEqual([]);
  });

  it("handles OSV.dev API failure gracefully", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network error"));

    const { scanVulnerabilities } = await import("../scanner/vulnerabilities");
    const result = await scanVulnerabilities([
      { name: "lodash", version: "4.17.20", ecosystem: "npm" },
    ]);
    expect(result).toEqual([]);
    fetchSpy.mockRestore();
  });

  it("parses OSV.dev response into VulnerabilityFinding", async () => {
    const mockResponse = {
      results: [
        {
          vulns: [
            {
              id: "GHSA-jf85-cpcp-j695",
              summary: "Prototype pollution in lodash",
              severity: [{ type: "CVSS_V3", score: "7.4" }],
              affected: [
                {
                  ranges: [{ type: "SEMVER", events: [{ introduced: "0" }, { fixed: "4.17.21" }] }],
                },
              ],
              references: [{ type: "ADVISORY", url: "https://github.com/advisories/GHSA-jf85-cpcp-j695" }],
            },
          ],
        },
      ],
    };

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    } as Response);

    const { scanVulnerabilities } = await import("../scanner/vulnerabilities");
    const result = await scanVulnerabilities([
      { name: "lodash", version: "4.17.20", ecosystem: "npm" },
    ]);

    expect(result.length).toBe(1);
    expect(result[0].cveId).toBe("GHSA-jf85-cpcp-j695");
    expect(result[0].severity).toBe("high");
    expect(result[0].cvssScore).toBe(7.4);
    expect(result[0].packageName).toBe("lodash");
    expect(result[0].fixVersion).toBe("4.17.21");
    expect(result[0].source).toBe("osv");
    fetchSpy.mockRestore();
  });

  it("maps CVSS scores to correct severity levels", async () => {
    const responses = [
      { score: "9.5", expected: "critical" },
      { score: "7.0", expected: "high" },
      { score: "4.5", expected: "medium" },
      { score: "2.0", expected: "low" },
    ];

    for (const { score, expected } of responses) {
      const mockResponse = {
        results: [
          {
            vulns: [
              {
                id: `CVE-${score}`,
                summary: "test",
                severity: [{ type: "CVSS_V3", score }],
              },
            ],
          },
        ],
      };

      const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const { scanVulnerabilities } = await import("../scanner/vulnerabilities");
      const result = await scanVulnerabilities([
        { name: "test-pkg", version: "1.0.0", ecosystem: "npm" },
      ]);

      expect(result[0].severity).toBe(expected);
      fetchSpy.mockRestore();
    }
  });

  it("deduplicates findings by CVE+package+version", async () => {
    const vuln = {
      id: "CVE-2021-12345",
      summary: "duplicate test",
      severity: [{ type: "CVSS_V3", score: "5.0" }],
    };

    const mockResponse = {
      results: [{ vulns: [vuln, vuln] }],
    };

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    } as Response);

    const { scanVulnerabilities } = await import("../scanner/vulnerabilities");
    const result = await scanVulnerabilities([
      { name: "pkg", version: "1.0.0", ecosystem: "npm" },
    ]);

    expect(result.length).toBe(1);
    fetchSpy.mockRestore();
  });

  it("handles missing severity as unknown", async () => {
    const mockResponse = {
      results: [{ vulns: [{ id: "CVE-no-severity", summary: "no severity" }] }],
    };

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    } as Response);

    const { scanVulnerabilities } = await import("../scanner/vulnerabilities");
    const result = await scanVulnerabilities([
      { name: "pkg", version: "1.0.0", ecosystem: "npm" },
    ]);

    expect(result[0].severity).toBe("unknown");
    expect(result[0].cvssScore).toBeNull();
    fetchSpy.mockRestore();
  });

  it("caps results at 200", async () => {
    const vulns = Array.from({ length: 250 }, (_, i) => ({
      id: `CVE-${i}`,
      summary: `vuln ${i}`,
      severity: [{ type: "CVSS_V3", score: "5.0" }],
    }));

    const mockResponse = { results: [{ vulns }] };

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    } as Response);

    const { scanVulnerabilities } = await import("../scanner/vulnerabilities");
    const result = await scanVulnerabilities([
      { name: "pkg", version: "1.0.0", ecosystem: "npm" },
    ]);

    expect(result.length).toBeLessThanOrEqual(200);
    fetchSpy.mockRestore();
  });
});
