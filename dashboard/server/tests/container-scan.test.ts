import { describe, it, expect, vi, beforeEach } from "vitest";

// We need to mock execFile in a way that works with promisify.
// promisify(execFile) wraps the callback-based execFile into a promise.
// The mock must accept callback-style arguments.
const mockExecFile = vi.fn();
vi.mock("child_process", () => ({
  execFile: mockExecFile,
}));

describe("container scanner", () => {
  beforeEach(() => {
    vi.resetModules();
    mockExecFile.mockReset();
  });

  function setupCalls(...calls: Array<{ error?: Error; stdout?: string }>) {
    let idx = 0;
    mockExecFile.mockImplementation((...args: any[]) => {
      // promisify wraps execFile so the callback is always the last arg
      const cb = args[args.length - 1];
      const call = calls[idx++] || { error: new Error("unexpected call") };
      if (typeof cb === "function") {
        if (call.error) cb(call.error, "", "");
        else cb(null, { stdout: call.stdout || "", stderr: "" });
      }
    });
  }

  it("returns unavailable when trivy is not found", async () => {
    setupCalls({ error: new Error("not found") });

    const { scanContainerImage } = await import("../scanner/container");
    const result = await scanContainerImage("nginx", "latest");
    expect(result.available).toBe(false);
    expect(result.error).toBeDefined();
  });

  it("parses trivy JSON output correctly", async () => {
    const trivyOutput = JSON.stringify({
      Results: [
        {
          Target: "nginx:latest (debian 11.6)",
          Vulnerabilities: [
            {
              VulnerabilityID: "CVE-2021-44228",
              PkgName: "liblog4j2-java",
              InstalledVersion: "2.14.0",
              FixedVersion: "2.17.0",
              Severity: "CRITICAL",
              Title: "Log4Shell",
            },
            {
              VulnerabilityID: "CVE-2022-0001",
              PkgName: "openssl",
              InstalledVersion: "1.1.1k",
              FixedVersion: "",
              Severity: "HIGH",
              Title: "Buffer overflow",
            },
          ],
        },
      ],
      Metadata: { OS: { Family: "debian", Name: "11.6" } },
    });

    setupCalls(
      { stdout: "/usr/local/bin/trivy" },  // which trivy
      { stdout: trivyOutput },              // trivy image
    );

    const { scanContainerImage } = await import("../scanner/container");
    const result = await scanContainerImage("nginx", "latest");

    expect(result.available).toBe(true);
    expect(result.image).toBe("nginx");
    expect(result.tag).toBe("latest");
    expect(result.totalVulnerabilities).toBe(2);
    expect(result.criticalCount).toBe(1);
    expect(result.highCount).toBe(1);
    expect(result.vulnerabilities[0].id).toBe("CVE-2021-44228");
    expect(result.vulnerabilities[0].severity).toBe("critical");
  });

  it("handles empty trivy results", async () => {
    const trivyOutput = JSON.stringify({
      Results: [{ Target: "alpine:latest", Vulnerabilities: null }],
      Metadata: { OS: { Family: "alpine", Name: "3.17" } },
    });

    setupCalls(
      { stdout: "/usr/local/bin/trivy" },
      { stdout: trivyOutput },
    );

    const { scanContainerImage } = await import("../scanner/container");
    const result = await scanContainerImage("alpine", "latest");

    expect(result.available).toBe(true);
    expect(result.totalVulnerabilities).toBe(0);
    expect(result.vulnerabilities).toEqual([]);
  });

  it("maps severity strings to lowercase", async () => {
    const trivyOutput = JSON.stringify({
      Results: [
        {
          Target: "test:latest",
          Vulnerabilities: [
            { VulnerabilityID: "CVE-1", PkgName: "a", InstalledVersion: "1", Severity: "MEDIUM", Title: "test" },
            { VulnerabilityID: "CVE-2", PkgName: "b", InstalledVersion: "1", Severity: "LOW", Title: "test" },
            { VulnerabilityID: "CVE-3", PkgName: "c", InstalledVersion: "1", Severity: "UNKNOWN", Title: "test" },
          ],
        },
      ],
    });

    setupCalls(
      { stdout: "/usr/local/bin/trivy" },
      { stdout: trivyOutput },
    );

    const { scanContainerImage } = await import("../scanner/container");
    const result = await scanContainerImage("test", "latest");

    expect(result.vulnerabilities[0].severity).toBe("medium");
    expect(result.vulnerabilities[1].severity).toBe("low");
    expect(result.vulnerabilities[2].severity).toBe("unknown");
  });
});
