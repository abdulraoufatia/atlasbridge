import { describe, it, expect, vi } from "vitest";
import type { ProviderClient, RepoContext } from "../scanner/types";

describe("remote scanner", () => {
  const mockCtx: RepoContext = {
    provider: "github",
    owner: "test-org",
    repo: "test-repo",
    branch: "main",
    accessToken: "ghp_test123",
  };

  it("returns result with languages and build systems", async () => {
    const mockClient: ProviderClient = {
      checkFiles: vi.fn().mockResolvedValue({}),
      getBranchProtection: vi.fn().mockResolvedValue(null),
      getRepoMetadata: vi.fn().mockResolvedValue(null),
      listTree: vi.fn().mockResolvedValue([
        "src/index.ts",
        "src/utils.ts",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        ".github/workflows/ci.yml",
        "README.md",
        "Dockerfile",
      ]),
      getFileContent: vi.fn().mockResolvedValue(null),
    };

    const { runRemoteScan } = await import("../scanner/remote");
    const result = await runRemoteScan(mockClient, mockCtx);

    expect(result.inventory.totalFiles).toBe(8);
    expect(result.inventory.languages.length).toBeGreaterThan(0);
    const tsLang = result.inventory.languages.find((l) => l.name === "TypeScript");
    expect(tsLang).toBeDefined();
    expect(result.scannedAt).toBeDefined();
  });

  it("detects CI platforms from file paths", async () => {
    const mockClient: ProviderClient = {
      checkFiles: vi.fn().mockResolvedValue({}),
      getBranchProtection: vi.fn().mockResolvedValue(null),
      getRepoMetadata: vi.fn().mockResolvedValue(null),
      listTree: vi.fn().mockResolvedValue([
        ".github/workflows/ci.yml",
        ".gitlab-ci.yml",
        "Jenkinsfile",
        "src/main.py",
      ]),
      getFileContent: vi.fn().mockResolvedValue(null),
    };

    const { runRemoteScan } = await import("../scanner/remote");
    const result = await runRemoteScan(mockClient, mockCtx);

    expect(result.inventory.ciPlatforms.length).toBeGreaterThanOrEqual(1);
  });

  it("detects sensitive paths", async () => {
    const mockClient: ProviderClient = {
      checkFiles: vi.fn().mockResolvedValue({}),
      getBranchProtection: vi.fn().mockResolvedValue(null),
      getRepoMetadata: vi.fn().mockResolvedValue(null),
      listTree: vi.fn().mockResolvedValue([
        "src/index.ts",
        ".env",
        ".env.production",
        "secrets.json",
        "config/credentials.yaml",
      ]),
      getFileContent: vi.fn().mockResolvedValue(null),
    };

    const { runRemoteScan } = await import("../scanner/remote");
    const result = await runRemoteScan(mockClient, mockCtx);

    expect(result.sensitivePaths.length).toBeGreaterThanOrEqual(1);
    const envEntry = result.sensitivePaths.find((sp) => sp.path === ".env");
    expect(envEntry).toBeDefined();
  });

  it("handles empty tree gracefully", async () => {
    const mockClient: ProviderClient = {
      checkFiles: vi.fn().mockResolvedValue({}),
      getBranchProtection: vi.fn().mockResolvedValue(null),
      getRepoMetadata: vi.fn().mockResolvedValue(null),
      listTree: vi.fn().mockResolvedValue([]),
      getFileContent: vi.fn().mockResolvedValue(null),
    };

    const { runRemoteScan } = await import("../scanner/remote");
    const result = await runRemoteScan(mockClient, mockCtx);

    expect(result.inventory.totalFiles).toBe(0);
    expect(result.inventory.languages).toEqual([]);
  });

  it("throws if listTree is not supported", async () => {
    const mockClient: ProviderClient = {
      checkFiles: vi.fn().mockResolvedValue({}),
      getBranchProtection: vi.fn().mockResolvedValue(null),
      getRepoMetadata: vi.fn().mockResolvedValue(null),
    };

    const { runRemoteScan } = await import("../scanner/remote");
    await expect(runRemoteScan(mockClient, mockCtx)).rejects.toThrow();
  });
});
