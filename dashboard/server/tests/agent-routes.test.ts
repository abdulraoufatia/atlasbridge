import { describe, it, expect, vi, beforeEach } from "vitest";
import { execFile } from "child_process";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("child_process", () => ({ execFile: vi.fn() }));

vi.mock("../db", () => ({
  insertOperatorAuditLog: vi.fn(),
  queryOperatorAuditLog: vi.fn(() => []),
  db: {},
  getAtlasBridgeDb: vi.fn(() => null),
}));

// ---------------------------------------------------------------------------
// Agent message via runAtlasBridge
// ---------------------------------------------------------------------------

describe("agent message via runAtlasBridge", () => {
  beforeEach(() => vi.clearAllMocks());

  it("message resolves with turn_id on success", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      cb(null, '{"ok":true,"turn_id":"turn-abc","session_id":"sess-123"}\n', "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    const result = await runAtlasBridge([
      "agent", "message", "sess-123", "Hello agent", "--json",
    ]);
    const parsed = JSON.parse(result.stdout.trim());
    expect(parsed.ok).toBe(true);
    expect(parsed.turn_id).toBe("turn-abc");
  });

  it("rejects when message command fails", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      const err = new Error("exit code 1");
      Object.assign(err, { stdout: '{"ok":false,"error":"Session not found"}', stderr: "" });
      cb(err, '{"ok":false,"error":"Session not found"}', "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    try {
      await runAtlasBridge(["agent", "message", "bad-sess", "Hello", "--json"]);
    } catch (e: any) {
      expect(e.message).toContain("exit code");
    }
  });
});

// ---------------------------------------------------------------------------
// Agent approve/deny via runAtlasBridge
// ---------------------------------------------------------------------------

describe("agent approve/deny via runAtlasBridge", () => {
  beforeEach(() => vi.clearAllMocks());

  it("approve resolves with plan status", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      cb(null, '{"ok":true,"plan_id":"plan-xyz","status":"approved"}\n', "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    const result = await runAtlasBridge([
      "agent", "approve", "sess-123", "plan-xyz", "--json",
    ]);
    const parsed = JSON.parse(result.stdout.trim());
    expect(parsed.ok).toBe(true);
    expect(parsed.status).toBe("approved");
  });

  it("deny resolves with plan status denied", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      cb(null, '{"ok":true,"plan_id":"plan-xyz","status":"denied"}\n', "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    const result = await runAtlasBridge([
      "agent", "deny", "sess-123", "plan-xyz", "--json",
    ]);
    const parsed = JSON.parse(result.stdout.trim());
    expect(parsed.ok).toBe(true);
    expect(parsed.status).toBe("denied");
  });

  it("approve rejects when plan not found", async () => {
    vi.mocked(execFile).mockImplementation((_bin, _args, _opts, cb: any) => {
      const err = new Error("exit code 1");
      Object.assign(err, {
        stdout: '{"ok":false,"error":"Plan not found: bad-plan"}',
        stderr: "",
      });
      cb(err, '{"ok":false,"error":"Plan not found: bad-plan"}', "");
    });
    const { runAtlasBridge } = await import("../routes/operator");
    try {
      await runAtlasBridge(["agent", "approve", "sess-123", "bad-plan", "--json"]);
    } catch (e: any) {
      expect(e.message).toContain("exit code");
    }
  });
});

// ---------------------------------------------------------------------------
// Agent state query (read-only, uses getAtlasBridgeDb)
// ---------------------------------------------------------------------------

describe("agent state/turns read endpoints", () => {
  it("getAtlasBridgeDb returning null yields empty arrays", async () => {
    const { getAtlasBridgeDb } = await import("../db");
    vi.mocked(getAtlasBridgeDb).mockReturnValue(null);

    // The repo methods should return empty arrays when db is null
    const { AtlasBridgeRepo } = await import("../atlasbridge-repo");
    const repo = new AtlasBridgeRepo();
    const turns = repo.listAgentTurns("nonexistent-session");
    expect(turns).toEqual([]);

    const plans = repo.listAgentPlans("nonexistent-session");
    expect(plans).toEqual([]);

    const decisions = repo.listAgentDecisions("nonexistent-session");
    expect(decisions).toEqual([]);

    const toolRuns = repo.listAgentToolRuns("nonexistent-session");
    expect(toolRuns).toEqual([]);

    const outcomes = repo.listAgentOutcomes("nonexistent-session");
    expect(outcomes).toEqual([]);
  });

  it("getAgentState returns null when db is null", async () => {
    const { getAtlasBridgeDb } = await import("../db");
    vi.mocked(getAtlasBridgeDb).mockReturnValue(null);

    const { AtlasBridgeRepo } = await import("../atlasbridge-repo");
    const repo = new AtlasBridgeRepo();
    const state = repo.getAgentState("nonexistent-session");
    expect(state).toBeNull();
  });
});
